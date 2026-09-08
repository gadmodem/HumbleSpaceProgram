// Entry point for the Humble Space Program mod (KSP2 Redux / SpaceWarp2).
//
// This file lives in the Unity mod project under Assets/HumbleSpaceProgram/Code/ and compiles against the
// game's Assembly-CSharp, SpaceWarp2.dll, ReduxLib.dll and 0Harmony.dll (all referenced by the asmdef
// the SDK generates) plus Unity.Addressables for key validation.
//
// Responsibilities:
//   1. Load assets/data/human_variety.json from the mod folder.
//   2. Install Harmony patches that swap the kerbal appearance tables for human ones
//      (VarietyPatches) and remap kerbal sound events to the mod's Wwise events (AudioRemapPatches).
//   3. After all addressables are loaded, drop table entries whose prefab/texture keys do not exist
//      yet, so a partially built asset set degrades to stock instead of breaking kerbal generation.

using System.Collections.Generic;
using System.IO;
using System.Linq;
using HarmonyLib;
using Newtonsoft.Json;
using Redux.ExtraModTypes;
using UnityEngine.AddressableAssets;

namespace HumbleSpaceProgram
{
    public sealed class HumbleSpaceProgramPlugin : KerbalMod
    {
        public const string ModGuid = "HumbleSpaceProgram";

        public static HumbleSpaceProgramPlugin Instance { get; private set; }
        public static HumanVarietyData Data { get; private set; }
        public static NarrationRemap Narration { get; private set; }
        private Harmony _harmony;

        public override void OnPreInitialized()
        {
            Instance = this;
            var dataPath = Path.Combine(SWMetadata.Folder.FullName, "assets", "data", "human_variety.json");
            if (!File.Exists(dataPath))
            {
                SWLogger.LogError($"Missing {dataPath}; the mod will stay dormant.");
                Data = new HumanVarietyData();
                return;
            }

            Data = JsonConvert.DeserializeObject<HumanVarietyData>(File.ReadAllText(dataPath)) ?? new HumanVarietyData();
            Data.BuildLookups();
            SWLogger.LogInfo($"Loaded variety data: {Data.GameObjectCategories.Count} categories, " +
                             $"{Data.WeightedOptions.Count} weighted tables, {Data.StockAudioEvents.Count} stock audio events, " +
                             $"{Data.AudioRemap.Count} explicit audio remaps.");

            // Harmony patches must be in place before the KerbalRosterManager constructs its
            // KerbalVarietySystem (main-menu game-instance load), so PreInitialized is the right hook.
            _harmony = CreateHarmonyAndPatchAll();
        }

        public override void OnInitialized()
        {
        }

        public override void OnPostInitialized()
        {
            // Every mod's addressables catalog is registered by now; prune entries we cannot serve.
            PruneMissingAssets();

            // The pre-rendered loading artwork is not part of a character prefab.  Only turn on its
            // addressable redirect once both forms of our replacement image are present; otherwise
            // an incomplete build keeps the stock screens instead of leaving the loading UI blank.
            var hasHumanLoadingScreen = KeyExists(HumanLoadingScreens.TextureAddress);
            if (hasHumanLoadingScreen)
            {
                HumanLoadingScreens.Enable();
            }
            else
            {
                SWLogger.LogWarning("Human loading-screen image is missing; stock loading screens stay in use.");
            }

            // The orientation film is skipped. The talking helper still needs a human sprite sheet.
            var hasHumanTalkingLoop = KeyExists(HumanGerbalTalkingLoop.SpriteSheetAddress);
            if (hasHumanTalkingLoop)
            {
                HumanGerbalTalkingLoop.Enable();
            }
            else
            {
                SWLogger.LogWarning("Human Gerbal talking-loop sheet is missing; stock helper frames stay in use.");
            }

            // Sound: load every bank in assets/soundbanks (SpaceWarp2's own loader throws in Redux 0.2.9, see
            // ModSoundbanks). Only events those banks define get remapped (word rule, explicit pairs, generated
            // narration table); the rest stay stock.
            var soundbanksDir = Path.Combine(SWMetadata.Folder.FullName, "assets", "soundbanks");
            ModSoundbanks.Load(soundbanksDir, msg => SWLogger.LogInfo(msg), msg => SWLogger.LogWarning(msg));
            var modEvents = SoundbankScan.EventIds(soundbanksDir, msg => SWLogger.LogWarning(msg));
            Narration = LoadNarrationRemap();
            AudioRemap.Configure(Data, Narration, modEvents, msg => SWLogger.LogInfo(msg), msg => SWLogger.LogWarning(msg));

            // Pre-built menu-room actors (Mission Control etc.): keep only the human parts that exist and
            // start loading them now so the swap at spawn time is synchronous.
            Data.ActorSwap.Prune(k => KeyExists(k.ToLowerInvariant() + ".prefab"), msg => SWLogger.LogWarning(msg));
            if (Data.ActorSwap.Enabled && !Data.ActorSwap.AllKeys().Any())
            {
                SWLogger.LogWarning("actorSwap: no human parts available, menu-room actors stay stock.");
                Data.ActorSwap.Enabled = false;
            }
            HumanActors.Preload(Data.ActorSwap);

            if (TestHooks.Enabled)
            {
                SWLogger.LogInfo("Test mode enabled (-humblespaceprogram-test).");
                StartCoroutine(TestHooks.Run(this));
            }
            else if (StartupResume.Enabled)
            {
                StartCoroutine(StartupResume.Run(this));
            }
            SWLogger.LogInfo($"Active: {Data.GameObjectCategories.Count} appearance categories, " +
                             $"{Data.WeightedOptions.Count} weighted tables, {Data.StringCategories.Count} name lists, " +
                             $"{AudioRemap.Count} audio remaps ({AudioRemap.NarrationCount} narration lines), " +
                             $"actor swap {(Data.ActorSwap.Enabled ? "on" : "off")}, " +
                             $"loading-screen swap {(hasHumanLoadingScreen ? "on" : "off")}, " +
                             $"intro videos skipped, autosave resume {(StartupResume.Enabled ? "on" : "off")}, " +
                             $"talking-loop swap {(hasHumanTalkingLoop ? "on" : "off")}.");
        }

        private NarrationRemap LoadNarrationRemap()
        {
            var path = Path.Combine(SWMetadata.Folder.FullName, "assets", "data", "narration_remap.json");
            if (!File.Exists(path)) return null;
            try
            {
                return JsonConvert.DeserializeObject<NarrationRemap>(File.ReadAllText(path));
            }
            catch (System.Exception e)
            {
                SWLogger.LogError($"Cannot read {path}: {e.Message}");
                return null;
            }
        }

        private static bool KeyExists(string key)
        {
            var handle = Addressables.LoadResourceLocationsAsync(key);
            var locations = handle.WaitForCompletion();
            var exists = locations != null && locations.Count > 0;
            Addressables.Release(handle);
            return exists;
        }

        private void PruneMissingAssets()
        {
            // GameObject categories: entries map to "<key lower>.prefab" (see Kerbal3DModel.PreloadAllAsyncAssets).
            foreach (var category in Data.GameObjectCategories.Keys.ToList())
            {
                var list = Data.GameObjectCategories[category];
                var kept = list.Where(k => KeyExists(k.ToLowerInvariant() + ".prefab")).ToList();
                var missing = list.Except(kept).ToList();
                if (missing.Count > 0)
                {
                    SWLogger.LogWarning($"Category {category}: {missing.Count} prefab(s) not found, skipped: {string.Join(", ", missing)}");
                }
                if (kept.Count == 0)
                {
                    SWLogger.LogWarning($"Category {category}: no human prefabs available, stock kerbal assets stay in use.");
                    Data.GameObjectCategories.Remove(category);
                }
                else
                {
                    Data.GameObjectCategories[category] = kept;
                }
            }

            foreach (var name in Data.WeightedOptions.Keys.ToList())
            {
                var table = Data.WeightedOptions[name];
                string suffix = null;
                if (string.Equals(table.Type, "GAMEOBJECT", System.StringComparison.OrdinalIgnoreCase)) suffix = ".prefab";
                else if (string.Equals(table.Type, "TEXTURE", System.StringComparison.OrdinalIgnoreCase)) suffix = ".png";
                if (suffix == null) continue; // COLOR tables need no assets

                var kept = table.WeightedOptionsArray
                    .Where(kv => KeyExists(kv.Key.ToLowerInvariant() + suffix))
                    .ToDictionary(kv => kv.Key, kv => kv.Value);
                var missing = table.WeightedOptionsArray.Keys.Except(kept.Keys).ToList();
                if (missing.Count > 0)
                {
                    SWLogger.LogWarning($"Weighted table {name}: {missing.Count} asset(s) not found, skipped: {string.Join(", ", missing)}");
                }
                if (kept.Count == 0)
                {
                    SWLogger.LogWarning($"Weighted table {name}: nothing available, stock table stays in use.");
                    Data.WeightedOptions.Remove(name);
                }
                else
                {
                    table.WeightedOptionsArray = kept;
                }
            }
        }
    }
}
