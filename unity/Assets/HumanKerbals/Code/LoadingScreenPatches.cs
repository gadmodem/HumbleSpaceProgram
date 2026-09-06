// Replaces the pre-rendered KSP2 loading-screen illustrations with the Human Kerbals artwork.
//
// The screen list in loadingscreens_assets_all.bundle is a TextAsset with one key for each KSC,
// Mission Control, VAB, recovery, crash and tutorial context.  These pictures are not scenes and do
// not contain a live character rig, so the actor conversion hook cannot reach them.  Redux presents
// every chosen key through UitkLoadingBar.SetImage; replacing that final assignment covers the whole
// list (and future additions) while leaving its fade and loading-flow lifecycle untouched.

using System.Collections;
using HarmonyLib;
using Redux.UI.LoadingFlow;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

namespace HumanKerbals
{
    internal static class HumanLoadingScreens
    {
        public const string TextureAddress = "human_loading_screen_texture";
        private static AsyncOperationHandle<Texture2D> _textureHandle;

        public static bool Enabled { get; private set; }

        public static void Enable()
        {
            if (Enabled) return;
            _textureHandle = Addressables.LoadAssetAsync<Texture2D>(TextureAddress);
            Enabled = true;
        }

        public static bool TryGetTexture(out Texture2D texture)
        {
            texture = null;
            if (!Enabled || !_textureHandle.IsValid() || !_textureHandle.IsDone ||
                _textureHandle.Status != AsyncOperationStatus.Succeeded) return false;
            texture = _textureHandle.Result;
            return texture != null;
        }

        public static IEnumerator ApplyWhenReady(UitkLoadingBar loadingBar)
        {
            while (_textureHandle.IsValid() && !_textureHandle.IsDone) yield return null;
            if (loadingBar != null && TryGetTexture(out var texture)) Apply(loadingBar, texture);
        }

        public static void Apply(UitkLoadingBar loadingBar, Texture2D texture)
        {
            // Data.BackgroundImage is the property bound to the UI Toolkit background.  The private
            // cache keeps the stock loading bar from reapplying its former texture on a later update.
            loadingBar.Data.BackgroundImage = texture;
            LoadedBackgroundRef(loadingBar) = texture;
        }

        private static readonly AccessTools.FieldRef<UitkLoadingBar, Texture2D> LoadedBackgroundRef =
            AccessTools.FieldRefAccess<UitkLoadingBar, Texture2D>("_loadedBackground");
    }

    [HarmonyPatch(typeof(UitkLoadingBar), "SetImage")]
    internal static class LoadingScreenPatches
    {
        [HarmonyPrefix]
        private static bool SetImage_Prefix(UitkLoadingBar __instance)
        {
            if (!HumanLoadingScreens.Enabled) return true;
            if (HumanLoadingScreens.TryGetTexture(out var texture))
            {
                HumanLoadingScreens.Apply(__instance, texture);
            }
            else
            {
                // Do not let a stock illustration flash while the local replacement is still loading.
                __instance.Data.BackgroundImage = null;
                __instance.StartCoroutine(HumanLoadingScreens.ApplyWhenReady(__instance));
            }
            return false;
        }
    }
}
