using System;
using System.Collections;
using System.IO;
using System.Linq;
using HarmonyLib;
using KSP.Game;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace HumbleSpaceProgram
{
    internal static class StartupResume
    {
        public static bool Enabled => !TestHooks.Enabled &&
            Array.IndexOf(Environment.GetCommandLineArgs(), "-humblespaceprogram-menu") < 0;

        private static string FindAutosave(HumbleSpaceProgramPlugin plugin)
        {
            var root = Path.Combine(Application.persistentDataPath, "Saves", "SinglePlayer");
            if (!Directory.Exists(root)) return null;
            foreach (var file in new DirectoryInfo(root).EnumerateFiles("*.json", SearchOption.AllDirectories)
                         .OrderByDescending(f => f.LastWriteTimeUtc))
            {
                try
                {
                    var metadata = JObject.Parse(File.ReadAllText(file.FullName))["Metadata"];
                    if (string.Equals((string)metadata?["SavedGameType"], "Auto", StringComparison.OrdinalIgnoreCase))
                        return file.FullName;
                }
                catch (Exception e)
                {
                    plugin.SWLogger.LogWarning($"Startup: skipping unreadable save {file.Name}: {e.Message}");
                }
            }
            return null;
        }

        public static IEnumerator Run(HumbleSpaceProgramPlugin plugin)
        {
            while (GameManager.Instance == null || GameManager.Instance.Game == null ||
                   GameManager.Instance.Game.GlobalGameState.GetState() != GameState.MainMenu)
                yield return null;
            // Let main-menu initialization finish before asking the load flow to unload it.
            yield return null;
            string save = null;
            try { save = FindAutosave(plugin); }
            catch (Exception e) { plugin.SWLogger.LogWarning("Startup: cannot enumerate autosaves: " + e.Message); }
            if (save == null)
            {
                plugin.SWLogger.LogWarning("Startup: no autosave found; main menu remains available.");
                yield break;
            }

            var game = GameManager.Instance.Game;
            var finished = false;
            var success = false;
            plugin.SWLogger.LogInfo("Startup: loading autosave " + save);
            try
            {
                if (!game.SaveLoadManager.LoadGameFromFile(save, (ticket, ok) => { success = ok; finished = true; }))
                    finished = true;
            }
            catch (Exception e)
            {
                plugin.SWLogger.LogError("Startup: autosave load failed: " + e);
                yield break;
            }
            var deadline = Time.realtimeSinceStartup + 300f;
            while (!finished && Time.realtimeSinceStartup < deadline) yield return null;
            if (!finished || !success)
            {
                plugin.SWLogger.LogWarning("Startup: autosave did not load successfully; Mission Control transition cancelled.");
                yield break;
            }
            yield return null;
            if (game.GlobalGameState.GetState() != GameState.MissionControl)
                game.TransitionToMissionControl();
            deadline = Time.realtimeSinceStartup + 60f;
            while (game.GlobalGameState.GetState() != GameState.MissionControl && Time.realtimeSinceStartup < deadline)
                yield return null;
            plugin.SWLogger.LogInfo("Startup: loaded autosave; state=" + game.GlobalGameState.GetState());
            var args = Environment.GetCommandLineArgs();
            var captureIndex = Array.IndexOf(args, "-humblespaceprogram-startup-capture");
            if (captureIndex >= 0 && captureIndex + 1 < args.Length &&
                game.GlobalGameState.GetState() == GameState.MissionControl)
            {
                var directory = args[captureIndex + 1].Trim('"');
                Directory.CreateDirectory(directory);
                for (var i = 1; i <= 3; i++)
                {
                    yield return new WaitForSecondsRealtime(10f);
                    ScreenCapture.CaptureScreenshot(Path.Combine(directory, $"startup_{i}.png"));
                }
                plugin.SWLogger.LogInfo("Startup: verification screenshots captured.");
            }
        }
    }

    [HarmonyPatch(typeof(GameManager), "CreateSplashScreens")]
    internal static class SkipStartupSplashScreens
    {
        [HarmonyPrefix]
        private static bool Prefix(GameManager __instance, Action resolve)
        {
            AccessTools.Method(typeof(GameManager), "OnSplashScreensFinished").Invoke(__instance, null);
            resolve();
            return false;
        }
    }
}
