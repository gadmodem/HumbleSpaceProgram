// Redirects stock kerbal Wwise events to the mod's own events without touching the stock banks.
//
// Every sound reaches Wwise through one of the sixteen AkSoundEngine.PostEvent overloads (eight take a
// GameObject, eight the Wwise game-object id; the GameObject ones call the native layer directly, so
// all sixteen are patched). The prefixes rewrite the event name or id before Wwise sees it:
//   * Animation events -> AnimationSoundHandler.PostAnimWWEvent -> KSPBaseAudio.PostEvent(string ...)
//     (footsteps, jumps, ladder, jetpack, helmet/gear adjust, flag plant, yawn)
//   * KSPPartAudio / KSPAudioEventManager -> KSPBaseAudio.PostEvent(string|uint ...)
//   * Wwise Unity components (AkEvent, AkAmbient) on prefabs -> PostEvent(uint ...)
//     (collision VO, explosion VO, ambient emitter, tutorial and briefing narration)
//
// Three sources feed the table, all filtered by the set of event ids the mod's own banks in
// assets/soundbanks define (SoundbankScan), so anything the banks do not provide keeps its stock sound:
//   1. the word rule (audioWordSwap in human_variety.json): a stock event whose name contains "Kerbal"
//      maps to the same name with "Gerbal" (Play_An_Kerbal_footsteps -> Play_An_Gerbal_footsteps);
//      stockAudioEvents lists the known names, names that arrive as strings are handled live;
//   2. explicit name pairs (audioRemap), for exceptions to the rule;
//   3. the generated narration table (assets/data/narration_remap.json, tools/vo_gerbal.py): stock
//      voice-over event ids whose line says "Kerbal" -> the "Gerbal" versions embedded in
//      HumbleSpaceProgram_narration.bnk.
// Wwise ids are FNV-1 32-bit hashes of the lower-cased name (WwiseHash), so names resolve to ids here.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using HarmonyLib;

namespace HumbleSpaceProgram
{
    internal static class WwiseHash
    {
        // Matches AK::SoundEngine::GetIDFromString (FNV-1, 32-bit, lower-case input).
        public static uint Fnv1(string name)
        {
            uint h = 2166136261u;
            foreach (var b in Encoding.UTF8.GetBytes(name.ToLowerInvariant()))
            {
                h = unchecked(h * 16777619u);
                h ^= b;
            }
            return h;
        }
    }

    /// Reads the event ids that .bnk files define (HIRC objects of type 4). Bank layout: sections of
    /// [4cc tag][u32 size]; HIRC = u32 count, then objects of [u8 type][u32 size][u32 id]...
    internal static class SoundbankScan
    {
        public static HashSet<uint> EventIds(string dir, Action<string> warn)
        {
            var ids = new HashSet<uint>();
            if (!Directory.Exists(dir)) return ids;
            foreach (var file in Directory.EnumerateFiles(dir, "*.bnk", SearchOption.AllDirectories))
            {
                try
                {
                    ids.UnionWith(EventIds(File.ReadAllBytes(file)));
                }
                catch (Exception e)
                {
                    warn($"Cannot read soundbank {file}: {e.Message}");
                }
            }
            return ids;
        }

        public static List<uint> EventIds(byte[] bank)
        {
            var list = new List<uint>();
            var off = 0;
            while (off + 8 <= bank.Length)
            {
                var tag = Encoding.ASCII.GetString(bank, off, 4);
                var size = (int)BitConverter.ToUInt32(bank, off + 4);
                if (tag == "HIRC" && off + 12 <= bank.Length)
                {
                    var count = BitConverter.ToUInt32(bank, off + 8);
                    var q = off + 12;
                    for (var i = 0; i < count && q + 9 <= bank.Length; i++)
                    {
                        var type = bank[q];
                        var objSize = (int)BitConverter.ToUInt32(bank, q + 1);
                        if (type == 4) list.Add(BitConverter.ToUInt32(bank, q + 5));
                        q += 5 + objSize;
                    }
                }
                off += 8 + size;
            }
            return list;
        }
    }

    /// Loads the mod's banks into Wwise. SpaceWarp2 has a "loading soundbanks" step for
    /// assets/soundbanks/*.bnk, but in Redux 0.2.9 its backend (SpaceWarp2.Sound.Backend.ISoundApi.Instance)
    /// is null at that point and the step throws, so nothing gets loaded; the plugin does it directly
    /// (LoadBankMemoryCopy: Wwise keeps its own copy, the managed buffer is released afterwards).
    internal static class ModSoundbanks
    {
        public static int Load(string dir, Action<string> info, Action<string> warn)
        {
            if (!Directory.Exists(dir)) return 0;
            if (!AkSoundEngine.IsInitialized())
            {
                warn("Wwise is not initialized yet; mod soundbanks not loaded.");
                return 0;
            }
            var loaded = 0;
            foreach (var file in Directory.EnumerateFiles(dir, "*.bnk", SearchOption.AllDirectories))
            {
                byte[] data;
                try
                {
                    data = File.ReadAllBytes(file);
                }
                catch (Exception e)
                {
                    warn($"Cannot read soundbank {file}: {e.Message}");
                    continue;
                }
                var handle = System.Runtime.InteropServices.GCHandle.Alloc(data, System.Runtime.InteropServices.GCHandleType.Pinned);
                try
                {
                    var result = AkSoundEngine.LoadBankMemoryCopy(handle.AddrOfPinnedObject(), (uint)data.Length, out var bankId);
                    if (result == AKRESULT.AK_Success || result == AKRESULT.AK_BankAlreadyLoaded)
                    {
                        loaded++;
                        info($"Soundbank {Path.GetFileName(file)} loaded ({data.Length / 1024} KB, bank id {bankId}, {result}).");
                    }
                    else
                    {
                        warn($"Soundbank {Path.GetFileName(file)} failed to load: {result}.");
                    }
                }
                finally
                {
                    handle.Free();
                }
            }
            return loaded;
        }
    }

    internal static class AudioRemap
    {
        private static readonly Dictionary<uint, uint> IdMap = new Dictionary<uint, uint>();
        private static readonly Dictionary<string, string> NameMap = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static readonly HashSet<string> Passthrough = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private static HashSet<uint> _modEvents = new HashSet<uint>();
        private static string _from;
        private static string _to;

        public static int Count => IdMap.Count;
        public static int NarrationCount { get; private set; }
        public static string RuleDescription => _from != null ? $"{_from} -> {_to}" : "off";

        public static void Configure(HumanVarietyData data, NarrationRemap narration, HashSet<uint> modEvents,
            Action<string> info, Action<string> warn)
        {
            IdMap.Clear();
            NameMap.Clear();
            Passthrough.Clear();
            NarrationCount = 0;
            _modEvents = modEvents ?? new HashSet<uint>();
            var swap = data.AudioWordSwap;
            var ruleOn = swap != null && swap.Enabled && !string.IsNullOrEmpty(swap.From) && !string.IsNullOrEmpty(swap.To);
            _from = ruleOn ? swap.From : null;
            _to = ruleOn ? swap.To : null;

            var skipped = new List<string>();
            if (_from != null)
            {
                foreach (var name in data.StockAudioEvents)
                {
                    var target = SwapWord(name);
                    if (target != null && !Add(name, target)) skipped.Add(target);
                }
            }
            foreach (var kv in data.AudioRemap)
            {
                if (!Add(kv.Key, kv.Value)) skipped.Add(kv.Value);
            }
            if (narration != null)
            {
                foreach (var line in narration.Lines)
                {
                    if (_modEvents.Contains(line.EventId))
                    {
                        IdMap[line.StockEventId] = line.EventId;
                        NarrationCount++;
                    }
                    else
                    {
                        skipped.Add(line.Event);
                    }
                }
            }
            info($"Audio: {_modEvents.Count} event(s) defined by the mod soundbanks; {IdMap.Count - NarrationCount} kerbal event remap(s) " +
                 $"and {NarrationCount} narration remap(s) active, word rule {RuleDescription}.");
            if (skipped.Count > 0)
            {
                warn($"Audio: {skipped.Count} remap target(s) not defined by any mod soundbank, stock sound kept: " +
                     string.Join(", ", skipped.Take(12)) + (skipped.Count > 12 ? ", ..." : ""));
            }
        }

        private static bool Add(string stockName, string modName)
        {
            var target = WwiseHash.Fnv1(modName);
            if (!_modEvents.Contains(target)) return false;
            NameMap[stockName] = modName;
            IdMap[WwiseHash.Fnv1(stockName)] = target;
            return true;
        }

        /// Replaces every occurrence of the swap word keeping the letter case of the original
        /// (Kerbal -> Gerbal, kerbal -> gerbal, KERBAL -> GERBAL); null when the name has no occurrence.
        public static string SwapWord(string name)
        {
            if (_from == null || string.IsNullOrEmpty(name)) return null;
            var idx = name.IndexOf(_from, StringComparison.OrdinalIgnoreCase);
            if (idx < 0) return null;
            var sb = new StringBuilder(name.Length + 8);
            var pos = 0;
            while (idx >= 0)
            {
                sb.Append(name, pos, idx - pos);
                sb.Append(MatchCase(name.Substring(idx, _from.Length), _to));
                pos = idx + _from.Length;
                idx = name.IndexOf(_from, pos, StringComparison.OrdinalIgnoreCase);
            }
            sb.Append(name, pos, name.Length - pos);
            return sb.ToString();
        }

        private static string MatchCase(string pattern, string word)
        {
            if (pattern.All(c => !char.IsLetter(c) || char.IsUpper(c))) return word.ToUpperInvariant();
            if (pattern.Length == word.Length)
            {
                var chars = word.ToCharArray();
                for (var i = 0; i < chars.Length; i++)
                {
                    chars[i] = char.IsUpper(pattern[i]) ? char.ToUpperInvariant(chars[i]) : char.ToLowerInvariant(chars[i]);
                }
                return new string(chars);
            }
            return char.IsUpper(pattern[0])
                ? char.ToUpperInvariant(word[0]) + word.Substring(1).ToLowerInvariant()
                : word.ToLowerInvariant();
        }

        public static void RemapName(ref string name)
        {
            if (name == null) return;
            if (NameMap.TryGetValue(name, out var mapped))
            {
                name = mapped;
                return;
            }
            if (_from == null || Passthrough.Contains(name)) return;
            var target = SwapWord(name);
            if (target != null && _modEvents.Contains(WwiseHash.Fnv1(target)))
            {
                NameMap[name] = target;
                name = target;
            }
            else
            {
                Passthrough.Add(name);
            }
        }

        public static void RemapId(ref uint id)
        {
            if (IdMap.TryGetValue(id, out var mapped)) id = mapped;
        }
    }

    /// Every PostEvent overload whose first parameter is the event id (four GameObject + four ulong).
    [HarmonyPatch]
    internal static class PostEventIdPatches
    {
        [HarmonyTargetMethods]
        private static IEnumerable<MethodBase> Targets() => typeof(AkSoundEngine)
            .GetMethods(BindingFlags.Public | BindingFlags.Static)
            .Where(m => m.Name == "PostEvent" && m.GetParameters().Length > 0 && m.GetParameters()[0].ParameterType == typeof(uint))
            .Cast<MethodBase>();

        [HarmonyPrefix]
        private static void Prefix(ref uint in_eventID) => AudioRemap.RemapId(ref in_eventID);
    }

    /// Every PostEvent overload whose first parameter is the event name.
    [HarmonyPatch]
    internal static class PostEventNamePatches
    {
        [HarmonyTargetMethods]
        private static IEnumerable<MethodBase> Targets() => typeof(AkSoundEngine)
            .GetMethods(BindingFlags.Public | BindingFlags.Static)
            .Where(m => m.Name == "PostEvent" && m.GetParameters().Length > 0 && m.GetParameters()[0].ParameterType == typeof(string))
            .Cast<MethodBase>();

        [HarmonyPrefix]
        private static void Prefix(ref string in_pszEventName) => AudioRemap.RemapName(ref in_pszEventName);
    }
}
