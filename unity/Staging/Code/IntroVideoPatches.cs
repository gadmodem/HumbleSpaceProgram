// Skips the orientation film and replaces the small talking-character loop with
// human Gerbal assets. The skipped film fires the stock completion event so its dialog closes.

using System;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;
using KSP.Video;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;
using UnityEngine.Video;

namespace HumbleSpaceProgram
{
    internal static class HumanGerbalTalkingLoop
    {
        public const string SpriteSheetAddress = "human_gerbal_intro_sheet";
        private const string StockLoopName = "Gif_Test_TalkingKerbal";
        private const int Columns = 2;
        private const int Rows = 3;
        private const int FramePixels = 128;

        private static readonly FieldInfo GifField = AccessTools.Field(typeof(LoopVideoData), "_gif");
        private static AsyncOperationHandle<Texture2D> _sheetHandle;
        private static LoopVideoData _replacement;
        private static bool _warned;

        public static bool Enabled { get; private set; }

        public static void Enable()
        {
            if (Enabled) return;
            _sheetHandle = Addressables.LoadAssetAsync<Texture2D>(SpriteSheetAddress);
            Enabled = true;
        }

        public static void ReplaceIfTalkingGerbal(ref LoopVideoData loopVideoData)
        {
            if (!Enabled || loopVideoData == null ||
                !string.Equals(loopVideoData.name, StockLoopName, StringComparison.Ordinal)) return;
            if (!TryGetReplacement(loopVideoData, out var replacement)) return;
            loopVideoData = replacement;
        }

        private static bool TryGetReplacement(LoopVideoData source, out LoopVideoData replacement)
        {
            replacement = _replacement;
            if (replacement != null) return true;
            if (GifField == null)
            {
                WarnOnce("Talking Gerbal loop: _gif field was not found; stock frames stay in use.");
                return false;
            }
            if (!_sheetHandle.IsValid()) return false;
            if (!_sheetHandle.IsDone) _sheetHandle.WaitForCompletion();
            var sheet = _sheetHandle.Status == AsyncOperationStatus.Succeeded ? _sheetHandle.Result : null;
            if (sheet == null || sheet.width != Columns * FramePixels || sheet.height != Rows * FramePixels)
            {
                WarnOnce("Talking Gerbal loop: expected a 256x384 human sprite sheet; stock frames stay in use.");
                return false;
            }

            var frames = new Sprite[Columns * Rows];
            for (var index = 0; index < frames.Length; index++)
            {
                var column = index % Columns;
                var rowFromTop = index / Columns;
                var y = sheet.height - (rowFromTop + 1) * FramePixels;
                frames[index] = Sprite.Create(
                    sheet,
                    new Rect(column * FramePixels, y, FramePixels, FramePixels),
                    new Vector2(0.5f, 0.5f),
                    100f,
                    0,
                    SpriteMeshType.FullRect);
                frames[index].name = $"HumanGerbalTalkingFrame_{index}";
            }

            _replacement = UnityEngine.Object.Instantiate(source);
            _replacement.name = "HumanGerbalTalkingLoop";
            GifField.SetValue(_replacement, frames);
            replacement = _replacement;
            HumbleSpaceProgramPlugin.Instance?.SWLogger.LogInfo("Talking Gerbal loop: replaced six stock frames.");
            return true;
        }

        private static void WarnOnce(string message)
        {
            if (_warned) return;
            _warned = true;
            HumbleSpaceProgramPlugin.Instance?.SWLogger.LogWarning(message);
        }
    }

    [HarmonyPatch]
    internal static class OrientationVideoPatches
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            var signature = new[] { typeof(LocalizedVideoData) };
            var open = AccessTools.Method(typeof(LocalizedVideoPlayer), "Open", signature);
            var openInternal = AccessTools.Method(typeof(LocalizedVideoPlayer), "OpenInternal", signature);
            if (open != null) yield return open;
            if (openInternal != null) yield return openInternal;
        }

        [HarmonyPrefix]
        private static bool Open_Prefix(LocalizedVideoPlayer __instance, LocalizedVideoData __0)
        {
            if (__0 == null || __0.VideoClip == null ||
                __0.VideoClip.name != "tutorial_01_SpaceisthePlace_v13") return true;
            // Complete on the next frame so the caller can finish opening the dialog and
            // register its completion listener. Close fires the game's normal finished event.
            HumbleSpaceProgramPlugin.Instance.StartCoroutine(Skip(__instance));
            return false;
        }

        private static System.Collections.IEnumerator Skip(LocalizedVideoPlayer player)
        {
            yield return null;
            if (player != null) player.Close();
            HumbleSpaceProgramPlugin.Instance?.SWLogger.LogInfo("Startup: skipped orientation video.");
        }
    }

    [HarmonyPatch]
    internal static class TalkingGerbalLoopPatches
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            var signature = new[] { typeof(LoopVideoData), typeof(Vector2), typeof(bool) };
            var player = AccessTools.Method(typeof(LoopPlayer), "Play", signature);
            var indicator = AccessTools.Method(typeof(LoopVideoPlayer), "Play", signature);
            if (player != null) yield return player;
            if (indicator != null) yield return indicator;
        }

        [HarmonyPrefix]
        private static void Play_Prefix(ref LoopVideoData __0)
        {
            HumanGerbalTalkingLoop.ReplaceIfTalkingGerbal(ref __0);
        }
    }
}
