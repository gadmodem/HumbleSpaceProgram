// Harmony patches that steer KSP2's data-driven kerbal appearance system (KerbalVarietySystem)
// toward the human asset set.
//
// Why patch instead of shipping replacement JSON:
//   KerbalVarietySystem.LoadVarietyTextAssets() loads every TextAsset labelled "kerbal_variety" and,
//   for the fixed-name files (KerbalVarietyGameObjectCategories.json, KerbalVarietyRangeRules.json),
//   calls LoadByLabel(<key>) and only accepts the result if exactly ONE asset came back. A second
//   catalog that reuses those keys therefore breaks loading instead of overriding it. Weighted tables
//   (*_weighted_*.json) are "last one wins" keyed by their inner Name, and string categories are
//   "first one wins", so the only robust way to replace everything is to intercept the lookups.
//
// What is patched:
//   * KerbalVarietySystem.GetVarietySubCategoryByRangeRule  -> returns the human list for GameObject
//     categories (BODY/HEAD/EYES/HAIR/HELMET/...) and string categories (names).
//   * KerbalVarietySystem.GetWeightedOptionsArrayByName     -> returns human weighted tables
//     (skin colour, eyes, facial hair, face details).
//   * VarietyUtils.GenerateSurname                          -> human surnames instead of "Kerman".
//   * KerbalVarietySystem.GenerateCustomKerbalAttributesFromRawData -> applies predefinedOverrides
//     to hero kerbals (Jebediah, Valentina, ...) before their attributes are generated.
//
// Everything downstream (Kerbal3DModel.PreloadAllAsyncAssets loading "<key>.prefab" through
// Addressables, the ReSkin/ReParent apply functions, portraits, IVA) works unchanged as long as the
// human prefabs follow the rig contract documented in docs/game-reference.md.

using System.Collections;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using KSP;
using KSP.Game;
using KSP.Modding.Variety;
using UnityEngine;

namespace HumbleSpaceProgram
{
    [HarmonyPatch]
    internal static class VarietyPatches
    {
        private static readonly Dictionary<string, WeightedOptionsArray> WeightedCache = new Dictionary<string, WeightedOptionsArray>();

        // ---- GameObject / string categories -------------------------------------------------

        [HarmonyPostfix]
        [HarmonyPatch(typeof(KerbalVarietySystem), nameof(KerbalVarietySystem.GetVarietySubCategoryByRangeRule))]
        private static void GetVarietySubCategoryByRangeRule_Postfix(VarietyRangeRule rangeRule, ref IList __result)
        {
            var data = HumbleSpaceProgramPlugin.Data;
            if (data == null) return;

            if (rangeRule.valueType == typeof(GameObject) &&
                data.GameObjectCategories.TryGetValue(rangeRule.subcategoryKey, out var goList) && goList.Count > 0)
            {
                __result = goList;
                return;
            }

            if (rangeRule.valueType == typeof(string) &&
                data.StringCategories.TryGetValue(rangeRule.subcategoryKey, out var strList) && strList.Count > 0)
            {
                __result = strList;
            }
        }

        // ---- Weighted tables (skin colour, eyes, facial hair, face detail) ----------------------

        private static WeightedOptionsArray HumanWeightedTable(string name, WeightedTable table)
        {
            if (!WeightedCache.TryGetValue(name, out var cached))
            {
                // JSONFriendlyWeightedOptionArray is the intermediate type the game deserialises the
                // *_weighted_options.json files into; building one keeps the game's own conversion logic.
                var middle = new JSONFriendlyWeightedOptionArray
                {
                    Name = name,
                    Type = table.Type,
                    WeightedOptionsArray = table.WeightedOptionsArray,
                };
                cached = new WeightedOptionsArray(middle);
                WeightedCache[name] = cached;
            }
            return cached;
        }

        [HarmonyPostfix]
        [HarmonyPatch(typeof(KerbalVarietySystem), nameof(KerbalVarietySystem.GetWeightedOptionsArrayByName))]
        private static void GetWeightedOptionsArrayByName_Postfix(string woaName, ref WeightedOptionsArray __result)
        {
            var data = HumbleSpaceProgramPlugin.Data;
            if (data == null || !data.WeightedOptions.TryGetValue(woaName, out var table)) return;
            __result = HumanWeightedTable(woaName, table);
        }

        // Attribute generation reads the private VarietyWeightedCategories dictionary directly
        // (PregenerateWeightedManifest), so swap our table in right before each weighted pick.
        private static readonly AccessTools.FieldRef<KerbalVarietySystem, Dictionary<string, WeightedOptionsArray>> WeightedCategoriesRef =
            AccessTools.FieldRefAccess<KerbalVarietySystem, Dictionary<string, WeightedOptionsArray>>("VarietyWeightedCategories");

        [HarmonyPrefix]
        [HarmonyPatch(typeof(KerbalVarietySystem), "PregenerateWeightedManifest")]
        private static void PregenerateWeightedManifest_Prefix(KerbalVarietySystem __instance, VarietyRangeRule rangeRule)
        {
            var data = HumbleSpaceProgramPlugin.Data;
            if (data == null || rangeRule.subcategoryKey == null || !data.WeightedOptions.TryGetValue(rangeRule.subcategoryKey, out var table)) return;
            var dict = WeightedCategoriesRef(__instance);
            if (dict == null) return;
            var ours = HumanWeightedTable(rangeRule.subcategoryKey, table);
            if (!dict.TryGetValue(rangeRule.subcategoryKey, out var current) || !ReferenceEquals(current, ours))
            {
                dict[rangeRule.subcategoryKey] = ours;
            }
        }

        // ---- Surnames -------------------------------------------------------------------------

        [HarmonyPrefix]
        [HarmonyPatch(typeof(VarietyUtils), nameof(VarietyUtils.GenerateSurname))]
        private static bool GenerateSurname_Prefix(ref KerbalAttributes kerbalAttributes, ref bool __result)
        {
            var data = HumbleSpaceProgramPlugin.Data;
            if (data == null || data.Surnames.Count == 0) return true; // fall through to stock "Kerman"

            var first = kerbalAttributes.GetAttribute("NAME")?.ToString() ?? string.Empty;
            var rng = KerbalVarietySystem.GetSeededRandomizer(first, string.Empty, "SURNAME");
            var surname = data.Surnames[rng.GetRandomInt32RangeMaxExcluded(0, data.Surnames.Count)];
            kerbalAttributes.SetAttribute("SURNAME", new VarietyPreloadInfo(surname, typeof(string), string.Empty));
            __result = true;
            return false;
        }

        // ---- Kerbals loaded from older saves ------------------------------------------------------

        // Saved kerbals carry their generated appearance keys (EYES_M_01, HAIR_F_03, ...). Before the
        // 3D model is built, swap any key listed in legacyRemap for its human counterpart; the change
        // sticks in the roster and gets saved with the game.
        [HarmonyPrefix]
        [HarmonyPatch(typeof(Kerbal3DModel), nameof(Kerbal3DModel.Build3DKerbal), new[] { typeof(KerbalAttributes) })]
        private static void Build3DKerbal_Prefix(KerbalAttributes kerbalAttributes)
        {
            var data = HumbleSpaceProgramPlugin.Data;
            if (data == null || data.LegacyRemap.Count == 0 || kerbalAttributes.Attributes == null) return; // KerbalAttributes is a struct; its Attributes dictionary is shared by reference

            foreach (var key in kerbalAttributes.Attributes.Keys.ToList())
            {
                var info = kerbalAttributes.Attributes[key];
                var value = info?.value as string;
                if (value == null || !data.LegacyRemap.TryGetValue(value, out var replacement)) continue;
                if (string.Equals(value, replacement, System.StringComparison.OrdinalIgnoreCase)) continue;
                info.value = replacement;
            }
        }

        // ---- Predefined (hero) kerbals --------------------------------------------------------

        [HarmonyPrefix]
        [HarmonyPatch(typeof(KerbalVarietySystem), nameof(KerbalVarietySystem.GenerateCustomKerbalAttributesFromRawData))]
        private static void GenerateCustomKerbalAttributesFromRawData_Prefix(Dictionary<string, object> rawCustomKerbalData)
        {
            var data = HumbleSpaceProgramPlugin.Data;
            if (data == null || rawCustomKerbalData == null) return;

            // The raw dictionary is the inner object of e.g. Jebediah_Kerman.json; the outer key
            // (JEBEDIAH_KERMAN) is rebuilt here from NAME + SURNAME to find overrides.
            var key = ($"{rawCustomKerbalData.GetValueSafe("NAME")}_{rawCustomKerbalData.GetValueSafe("SURNAME")}").ToUpperInvariant();
            if (!data.PredefinedOverrides.TryGetValue(key, out var overrides)) return;
            foreach (var kv in overrides)
            {
                rawCustomKerbalData[kv.Key] = kv.Value;
            }
        }
    }
}
