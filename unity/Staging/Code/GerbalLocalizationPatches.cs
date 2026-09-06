// Ensures terms returned through I2 localization follow the mod's player-facing name: Gerbal.

using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using HarmonyLib;
using I2.Loc;

namespace HumbleSpaceProgram
{
    internal static class GerbalTerminology
    {
        public static string ReplaceKerbal(string text)
        {
            if (string.IsNullOrEmpty(text)) return text;
            const string stock = "Kerbal";
            const string replacement = "Gerbal";
            var index = text.IndexOf(stock, StringComparison.OrdinalIgnoreCase);
            if (index < 0) return text;

            var output = new StringBuilder(text.Length + 8);
            var position = 0;
            while (index >= 0)
            {
                output.Append(text, position, index - position);
                output.Append(MatchCase(text.Substring(index, stock.Length), replacement));
                position = index + stock.Length;
                index = text.IndexOf(stock, position, StringComparison.OrdinalIgnoreCase);
            }
            output.Append(text, position, text.Length - position);
            return output.ToString();
        }

        private static string MatchCase(string source, string replacement)
        {
            var allCaps = true;
            for (var i = 0; i < source.Length; i++)
            {
                if (char.IsLetter(source[i]) && !char.IsUpper(source[i])) { allCaps = false; break; }
            }
            if (allCaps) return replacement.ToUpperInvariant();

            var letters = replacement.ToCharArray();
            for (var i = 0; i < letters.Length && i < source.Length; i++)
            {
                letters[i] = char.IsUpper(source[i])
                    ? char.ToUpperInvariant(letters[i])
                    : char.ToLowerInvariant(letters[i]);
            }
            return new string(letters);
        }
    }

    [HarmonyPatch]
    internal static class GerbalLocalizationPatches
    {
        // Both public return-string paths are included.  The result patch is intentionally late in the
        // localization flow, preserving stock format parameters, pluralization, RTL handling, and fallback.
        private static IEnumerable<MethodBase> TargetMethods()
        {
            const BindingFlags flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
            foreach (var method in typeof(LocalizationManager).GetMethods(flags))
            {
                if (method.ReturnType != typeof(string)) continue;
                if (method.Name == "GetTranslation" || method.Name == "GetTermTranslation") yield return method;
            }
        }

        [HarmonyPostfix]
        private static void GetTranslation_Postfix(ref string __result)
        {
            __result = GerbalTerminology.ReplaceKerbal(__result);
        }
    }
}
