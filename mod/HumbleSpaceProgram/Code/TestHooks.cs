// Automated in-game test support (only active with -humblespaceprogram-test on the command line).
//
//   KSP2_x64.exe -humblespaceprogram-test -humblespaceprogram-load "<save.json>" -humblespaceprogram-portraits "<dir>"
//
// Once the main menu is up the hook loads the given save through the game's SaveLoadManager. Loading
// a campaign makes KerbalRosterManager build a Kerbal3DModel for every roster kerbal to shoot its
// portrait (KerbalPhotoBooth), which exercises the human body/head/eyes/hair prefabs. Every finished
// portrait is written as PNG to the portraits directory; after the roster is done (or a timeout) the
// game quits so tools/verify_in_game.ps1 can collect the results.
//
//   KSP2_x64.exe -humblespaceprogram-test -humblespaceprogram-audiotest
//
// Audio mode instead posts the first stock narration events that the mod remaps (see
// AudioRemapPatches.cs) from the main menu and logs what Wwise does with them: the playing id (0 means
// the event is unknown), the clip duration Wwise reports (must match the embedded PCM length), when
// the event ends, and every Wwise monitor error raised meanwhile.

using System;
using System.Collections;
using System.IO;
using System.Linq;
using KSP.Game;
using KSP.Messages;
using UnityEngine;

namespace HumbleSpaceProgram
{
    internal static class TestHooks
    {
        public static bool Enabled => Array.IndexOf(Environment.GetCommandLineArgs(), "-humblespaceprogram-test") >= 0;

        private static string Arg(string name)
        {
            var args = Environment.GetCommandLineArgs();
            var i = Array.IndexOf(args, name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1].Trim('"') : null;
        }

        public static IEnumerator Run(HumbleSpaceProgramPlugin plugin)
        {
            var log = plugin.SWLogger;
            var savePath = Arg("-humblespaceprogram-load");
            var portraitDir = Arg("-humblespaceprogram-portraits") ?? Path.Combine(plugin.SWMetadata.Folder.FullName, "..", "..", "HumbleSpaceProgram_portraits");
            Directory.CreateDirectory(portraitDir);
            log.LogInfo($"TEST: waiting for main menu (save: {savePath ?? "none"}, portraits: {portraitDir})");

            // Wait for the game instance and the main menu state.
            while (true)
            {
                var game = GameManager.Instance != null ? GameManager.Instance.Game : null;
                if (game != null && game.GlobalGameState != null)
                {
                    var cfg = game.GlobalGameState.GetGameState();
                    if (cfg != null && cfg.GameState == GameState.MainMenu) break;
                }
                yield return new WaitForSeconds(1f);
            }
            yield return new WaitForSeconds(3f);

            if (Array.IndexOf(Environment.GetCommandLineArgs(), "-humblespaceprogram-audiotest") >= 0)
            {
                yield return AudioTest(plugin);
                log.LogInfo("TEST: done");
                yield return new WaitForSeconds(2f);
                Application.Quit();
                yield break;
            }

            var gameInstance = GameManager.Instance.Game;
            var portraits = 0;
            var lastPortrait = Time.realtimeSinceStartup;
            Action<MessageCenterMessage> onPortrait = msg =>
            {
                var info = (msg as KerbalPortraitFinished)?.Kerbal;
                if (info == null || info.Portrait == null) return;
                try
                {
                    var tex = info.Portrait.texture;
                    var bytes = tex.EncodeToPNG();
                    var name = info.Attributes.GetFullName().Replace(' ', '_');
                    File.WriteAllBytes(Path.Combine(portraitDir, name + ".png"), bytes);
                    portraits++;
                    lastPortrait = Time.realtimeSinceStartup;
                    log.LogInfo($"TEST: wrote portrait {name} ({tex.width}x{tex.height})");
                }
                catch (Exception e)
                {
                    log.LogError("TEST: portrait write failed: " + e);
                }
            };
            gameInstance.Messages.PersistentSubscribe<KerbalPortraitFinished>(onPortrait);

            if (!string.IsNullOrEmpty(savePath) && File.Exists(savePath))
            {
                log.LogInfo("TEST: loading save " + savePath);
                var loadFinished = false;
                var loadOk = false;
                gameInstance.SaveLoadManager.LoadGameFromFile(savePath, (ticket, success) =>
                {
                    loadFinished = true;
                    loadOk = success;
                });
                var t0 = Time.realtimeSinceStartup;
                while (!loadFinished && Time.realtimeSinceStartup - t0 < 300f) yield return null;
                log.LogInfo($"TEST: load finished={loadFinished} success={loadOk} after {Time.realtimeSinceStartup - t0:F1}s");
            }
            else
            {
                log.LogWarning("TEST: no save to load; staying in the main menu.");
            }

            // Give the roster time to shoot portraits: stop 20 s after the last one (or 120 s max).
            var start = Time.realtimeSinceStartup;
            lastPortrait = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - start < 120f && Time.realtimeSinceStartup - lastPortrait < 20f)
            {
                yield return new WaitForSeconds(1f);
            }
            log.LogInfo($"TEST: {portraits} portraits written to {portraitDir}");

            // Optional: walk into Mission Control and photograph the pre-built actors after the swap.
            var mcDir = Arg("-humblespaceprogram-missioncontrol");
            if (!string.IsNullOrEmpty(mcDir))
            {
                Directory.CreateDirectory(mcDir);
                log.LogInfo("TEST: entering Mission Control");
                gameInstance.TransitionToMissionControl();
                var t1 = Time.realtimeSinceStartup;
                while (Time.realtimeSinceStartup - t1 < 60f && gameInstance.GlobalGameState.GetState() != GameState.MissionControl)
                {
                    yield return new WaitForSeconds(1f);
                }
                log.LogInfo($"TEST: state {gameInstance.GlobalGameState.GetState()} after {Time.realtimeSinceStartup - t1:F1}s");
                var delays = new[] { 8f, 10f, 15f };
                for (var i = 0; i < delays.Length; i++)
                {
                    yield return new WaitForSeconds(delays[i]);
                    var file = Path.Combine(mcDir, $"missioncontrol_{i + 1}.png");
                    ScreenCapture.CaptureScreenshot(file);
                    yield return null;
                    yield return null;
                    log.LogInfo($"TEST: screenshot {file} (actor rigs converted so far: {HumanActors.SwappedRigs})");
                }
            }

            log.LogInfo("TEST: done");
            yield return new WaitForSeconds(2f);
            Application.Quit();
        }

        private static IEnumerator AudioTest(HumbleSpaceProgramPlugin plugin)
        {
            var log = plugin.SWLogger;
            var narration = HumbleSpaceProgramPlugin.Narration;
            AkCallbackManager.SetMonitoringCallback(AkMonitorErrorLevel.ErrorLevel_All,
                (code, level, playingId, gameObj, msg) => log.LogInfo($"AUDIO: wwise {level} {code}: {msg} (playing {playingId})"));
            var go = plugin.gameObject;
            var registered = AkSoundEngine.RegisterGameObj(go, "HumbleSpaceProgramAudioTest");
            log.LogInfo($"AUDIO: RegisterGameObj -> {registered}; {AudioRemap.Count} remaps active " +
                        $"({AudioRemap.NarrationCount} narration), word rule {AudioRemap.RuleDescription}");
            if (narration == null || narration.Lines.Count == 0)
            {
                log.LogWarning("AUDIO: no narration remap table, nothing to play.");
                yield break;
            }

            var count = Math.Min(3, narration.Lines.Count);
            for (var i = 0; i < count; i++)
            {
                var line = narration.Lines[i];
                var finished = false;
                var durationMs = -1f;
                var estimatedMs = -1f;
                AkCallbackManager.EventCallback cb = (cookie, type, info) =>
                {
                    if (type == AkCallbackType.AK_Duration && info is AkDurationCallbackInfo d)
                    {
                        durationMs = d.fDuration;
                        estimatedMs = d.fEstimatedDuration;
                    }
                    if (type == AkCallbackType.AK_EndOfEvent) finished = true;
                };
                var t0 = Time.realtimeSinceStartup;
                // The prefix in AudioRemapPatches rewrites the stock id to the mod event before Wwise sees it.
                var playingId = AkSoundEngine.PostEvent(line.StockEventId, go,
                    (uint)(AkCallbackType.AK_EndOfEvent | AkCallbackType.AK_Duration), cb, null);
                log.LogInfo($"AUDIO: posted stock event {line.StockEventId} (-> {line.Event} {line.EventId}) playingId={playingId}, " +
                            $"clip {line.Seconds:F2}s: \"{line.Text}\"");
                if (playingId == 0) continue;
                while (!finished && Time.realtimeSinceStartup - t0 < line.Seconds + 6f) yield return null;
                log.LogInfo($"AUDIO: event {line.StockEventId} finished={finished} after {Time.realtimeSinceStartup - t0:F2}s, " +
                            $"wwise duration {durationMs / 1000f:F2}s (estimated {estimatedMs / 1000f:F2}s), expected {line.Seconds:F2}s");
            }
        }
    }
}
