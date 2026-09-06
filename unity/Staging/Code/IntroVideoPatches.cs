// Replaces the pre-rendered orientation film and the small talking-character loop with
// human Gerbal assets.  The stock video player continues to own playback, narration, subtitles,
// controls, and close behavior; only its incoming visual asset is redirected.

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
    internal static class HumanGerbalOrientationVideo
    {
        public const string VideoAddress = "human_gerbal_orientation_video";
        private const string StockOrientationClipName = "tutorial_01_SpaceisthePlace_v13";

        private static readonly FieldInfo VideoClipField =
            AccessTools.Field(typeof(LocalizedVideoData), "m_videoClip");
        private static AsyncOperationHandle<VideoClip> _videoHandle;
        private static LocalizedVideoData _replacement;
        private static bool _warned;

        public static bool Enabled { get; private set; }

        public static void Enable()
        {
            if (Enabled) return;
            _videoHandle = Addressables.LoadAssetAsync<VideoClip>(VideoAddress);
            Enabled = true;
        }

        private static bool TryGetReplacement(LocalizedVideoData source, out LocalizedVideoData replacement)
        {
            replacement = _replacement;
            if (replacement != null) return true;
            if (VideoClipField == null)
            {
                WarnOnce("Orientation video: m_videoClip field was not found; stock orientation film stays in use.");
                return false;
            }
            if (!_videoHandle.IsValid()) return false;
            if (!_videoHandle.IsDone) _videoHandle.WaitForCompletion();
            if (_videoHandle.Status != AsyncOperationStatus.Succeeded || _videoHandle.Result == null)
            {
                WarnOnce("Orientation video: human Gerbal replacement could not be loaded; stock orientation film stays in use.");
                return false;
            }

            // Cloning retains the stock video data's subtitle and Wwise event references.  The audio
            // remapper can therefore supply the Gerbal narration without reimplementing this player.
            _replacement = UnityEngine.Object.Instantiate(source);
            _replacement.name = "HumanGerbalOrientationData";
            VideoClipField.SetValue(_replacement, _videoHandle.Result);
            replacement = _replacement;
            HumbleSpaceProgramPlugin.Instance?.SWLogger.LogInfo(
                $"Orientation video: {StockOrientationClipName} -> {_videoHandle.Result.name}.");
            return true;
        }

        private static void WarnOnce(string message)
        {
            if (_warned) return;
            _warned = true;
            HumbleSpaceProgramPlugin.Instance?.SWLogger.LogWarning(message);
        }

        internal static void CaptureSourceAndReplace(ref LocalizedVideoData videoData)
        {
            if (!Enabled || videoData == null || videoData.VideoClip == null ||
                !string.Equals(videoData.VideoClip.name, StockOrientationClipName, StringComparison.Ordinal)) return;
            if (TryGetReplacement(videoData, out var replacement)) videoData = replacement;
        }
    }

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
        private static void Open_Prefix(ref LocalizedVideoData __0)
        {
            HumanGerbalOrientationVideo.CaptureSourceAndReplace(ref __0);
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
