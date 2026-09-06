// Humanises the pre-built kerbal "actors" the game drops into its menu rooms.
//
// Mission Control (and the main-menu vignettes) do not use roster kerbals. Their scene holds
// RandomPrefabLoader components that instantiate finished RPLT_* prefabs: a stock rig, a body mesh
// (mesh_body_scientist_01, ...), both stock heads, every stock hairstyle/eye/glasses/beard mesh, and a
// ShowRandomMeshByKerbalType component that hides all but one variant. Nothing goes through
// KerbalVarietySystem or Kerbal3DModel, so VarietyPatches never sees them.
//
// RandomPrefabLoader_Target.Init runs right after each actor prefab is instantiated (both the
// RandomPrefabLoader path and the main-menu MainMenuVesselRotationSession path call it). The postfix
// below finds every kerbal rig inside the spawned prefab and, exactly like the game's own
// VarietyUtils.ReSkinTheseMeshesToTheRootRig / ReParentAllMeshesToTheRootRig / AttachToNamedParent:
//   * re-binds the human body and head SkinnedMeshRenderers to the actor's bones by name,
//   * re-parents the human eye meshes under the eye/lid bones (local transform kept),
//   * attaches a human hairstyle (and helmet, if the actor wears one) with identity local transform,
//   * hides the stock body/head/eye/hair (and optionally beard/glasses) objects.
// The actor keeps its own Animator, fidget, blinking and picker components, so it animates as before.
// ActorMaterialColors is switched off for converted actors: it only knows the KSP2 character shaders,
// and its face-detail step would paint a stock kerbal face texture onto the human head material.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using KSP.Game;
using KSP.Sim;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

namespace HumanKerbals
{
    /// Marks a spawned actor prefab that has been (or is being) converted.
    public sealed class HumanActorMarker : MonoBehaviour
    {
    }

    [HarmonyPatch]
    internal static class ActorPatches
    {
        [HarmonyPostfix]
        [HarmonyPatch(typeof(RandomPrefabLoader_Target), nameof(RandomPrefabLoader_Target.Init))]
        private static void Init_Postfix(RandomPrefabLoader_Target __instance, List<GameState> validGameStates)
        {
            try
            {
                HumanActors.OnActorSpawned(__instance, validGameStates);
            }
            catch (Exception e)
            {
                HumanKerbalsPlugin.Instance?.SWLogger.LogError("Actor swap failed: " + e);
            }
        }

        // Face-detail textures are stock kerbal face albedos; never let them land on a human head.
        [HarmonyPrefix]
        [HarmonyPatch(typeof(ActorMaterialColors), "TryApplyAllTextures")]
        private static bool TryApplyAllTextures_Prefix(ActorMaterialColors __instance)
        {
            return __instance.GetComponentInParent<HumanActorMarker>() == null;
        }
    }

    internal static class HumanActors
    {
        private static readonly Dictionary<string, AsyncOperationHandle<GameObject>> Handles =
            new Dictionary<string, AsyncOperationHandle<GameObject>>(StringComparer.OrdinalIgnoreCase);

        /// Rigs converted so far (test hooks report it).
        public static int SwappedRigs { get; private set; }

        private static bool Ready
        {
            get
            {
                foreach (var h in Handles.Values)
                {
                    if (!h.IsDone) return false;
                }
                return true;
            }
        }

        /// Starts loading every human prefab the actor swap can use, so the swap itself is synchronous.
        public static void Preload(ActorSwapData data)
        {
            if (data == null) return;
            foreach (var key in data.AllKeys().Distinct(StringComparer.OrdinalIgnoreCase))
            {
                if (Handles.ContainsKey(key)) continue;
                Handles[key] = Addressables.LoadAssetAsync<GameObject>(key.ToLowerInvariant() + ".prefab");
            }
        }

        private static GameObject Prefab(string key)
        {
            if (string.IsNullOrEmpty(key) || !Handles.TryGetValue(key, out var h) || !h.IsDone) return null;
            return h.Status == AsyncOperationStatus.Succeeded ? h.Result : null;
        }

        private static GameObject FirstPrefab(IEnumerable<string> keys)
        {
            if (keys == null) return null;
            foreach (var k in keys)
            {
                var p = Prefab(k);
                if (p != null) return p;
            }
            return null;
        }

        public static void OnActorSpawned(RandomPrefabLoader_Target target, List<GameState> validStates)
        {
            var data = HumanKerbalsPlugin.Data?.ActorSwap;
            if (data == null || !data.Enabled || target == null) return;
            var root = target.gameObject;
            if (root.GetComponent<HumanActorMarker>() != null) return;
            if (FindDeep(root.transform, "bone_kerbal_master_parent") == null) return; // no kerbal inside

            // Init destroys the prefab when the current game state is not one it is meant for.
            var game = GameManager.Instance != null ? GameManager.Instance.Game : null;
            if (game != null && validStates != null && validStates.Count > 0 &&
                !validStates.Contains(game.GlobalGameState.GetState()))
            {
                return;
            }

            root.AddComponent<HumanActorMarker>();
            DisableActorColors(root);
            if (Ready)
            {
                Apply(root);
            }
            else
            {
                HumanKerbalsPlugin.Instance.StartCoroutine(ApplyWhenReady(root));
            }
        }

        private static IEnumerator ApplyWhenReady(GameObject root)
        {
            while (!Ready) yield return null;
            if (root != null) Apply(root);
        }

        private static void DisableActorColors(GameObject root)
        {
            foreach (var amc in root.GetComponentsInChildren<ActorMaterialColors>(true))
            {
                amc.StopAllCoroutines();
                amc.RandomizeFaceDetailsAtRuntime = false;
                amc.FaceDetail = null;
                amc.enabled = false;
            }
        }

        private static void Apply(GameObject root)
        {
            var data = HumanKerbalsPlugin.Data.ActorSwap;
            var masters = root.GetComponentsInChildren<Transform>(true).Where(t => t.name == "bone_kerbal_master_parent").ToList();
            foreach (var master in masters)
            {
                try
                {
                    if (SwapRig(master, data)) SwappedRigs++;
                }
                catch (Exception e)
                {
                    HumanKerbalsPlugin.Instance.SWLogger.LogError($"Actor swap failed for {Path(master)}: {e}");
                }
            }
        }

        private static bool SwapRig(Transform master, ActorSwapData data)
        {
            var log = HumanKerbalsPlugin.Instance.SWLogger;
            var rig = master.parent;
            if (rig == null) return false;
            var layer = rig.gameObject.layer;
            var bones = new Dictionary<string, Transform>();
            foreach (var t in master.GetComponentsInChildren<Transform>(true))
            {
                if (!bones.ContainsKey(t.name)) bones[t.name] = t;
            }

            // Stock renderers that sit on the rig (siblings of the master bone), classified by name.
            var skinned = rig.GetComponentsInChildren<SkinnedMeshRenderer>(true)
                .Where(s => !s.transform.IsChildOf(master)).ToList();
            var stockHeads = skinned.Where(s => s.name.IndexOf("_head_", StringComparison.OrdinalIgnoreCase) >= 0).ToList();
            var stockBodies = skinned.Where(s => BodyKind(s.name, data) != null).ToList();
            var female = IsFemale(rig, stockHeads);
            var tag = female ? "f" : "m";

            var changed = false;

            // ---- body -------------------------------------------------------------------------------
            if (stockBodies.Count > 0)
            {
                var kind = BodyKind(stockBodies[0].name, data);
                data.Bodies.TryGetValue(kind, out var candidates);
                var prefab = FirstPrefab(candidates);
                if (prefab == null)
                {
                    log.LogWarning($"Actor {Path(rig)}: no human body available for '{kind}', stock body kept.");
                }
                else if (AddSkinned(prefab, rig, master, bones, layer))
                {
                    foreach (var s in stockBodies) s.gameObject.SetActive(false);
                    changed = true;
                }
            }

            // ---- head, eyes, hair -----------------------------------------------------------------
            data.Heads.TryGetValue(tag, out var headKey);
            var headPrefab = Prefab(headKey);
            if (stockHeads.Count > 0 && headPrefab != null && AddSkinned(headPrefab, rig, master, bones, layer))
            {
                foreach (var s in stockHeads) s.gameObject.SetActive(false);
                changed = true;

                data.Eyes.TryGetValue(tag, out var eyesKey);
                var eyesPrefab = Prefab(eyesKey);
                if (eyesPrefab != null)
                {
                    foreach (var mr in master.GetComponentsInChildren<MeshRenderer>(true))
                    {
                        if (mr.name.StartsWith("mesh_eye", StringComparison.OrdinalIgnoreCase)) mr.gameObject.SetActive(false);
                    }
                    AddReparented(eyesPrefab, bones, layer);
                }

                if (bones.TryGetValue("bone_kerbal_head", out var head))
                {
                    foreach (Transform child in head)
                    {
                        // actor_hairstyles, hair_jeb, keri_hair, ... (the human style is attached after this loop)
                        if (child.name.IndexOf("hair", StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            child.gameObject.SetActive(false);
                        }
                        if (data.HideGlasses && child.name.IndexOf("glasses", StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            child.gameObject.SetActive(false);
                        }
                    }
                    data.Hair.TryGetValue(tag, out var hairKeys);
                    var hairPrefab = PickPrefab(hairKeys);
                    if (hairPrefab != null) Attach(hairPrefab, head, layer);
                }

                if (data.HideFacialHair)
                {
                    foreach (var s in skinned)
                    {
                        if (s.name.IndexOf("facialhair", StringComparison.OrdinalIgnoreCase) >= 0) s.gameObject.SetActive(false);
                    }
                    foreach (Transform child in rig)
                    {
                        if (child.name.Equals("facialhair", StringComparison.OrdinalIgnoreCase)) child.gameObject.SetActive(false);
                    }
                }
            }
            else if (stockHeads.Count > 0)
            {
                log.LogWarning($"Actor {Path(rig)}: human head '{headKey}' not available, stock head kept.");
            }

            // ---- helmet (spacesuit actors only) ------------------------------------------------------
            if (bones.TryGetValue("bone_kerbal_helmet", out var helmetBone))
            {
                var stockHelmet = new List<Transform>();
                foreach (Transform child in helmetBone)
                {
                    if (child.name.IndexOf("helm", StringComparison.OrdinalIgnoreCase) >= 0 &&
                        child.GetComponentInChildren<Renderer>(true) != null)
                    {
                        stockHelmet.Add(child);
                    }
                }
                var helmetPrefab = Prefab(data.Helmet);
                if (stockHelmet.Count > 0 && helmetPrefab != null)
                {
                    foreach (var h in stockHelmet) h.gameObject.SetActive(false);
                    Attach(helmetPrefab, helmetBone, layer);
                    changed = true;
                }
            }

            if (changed)
            {
                var animator = rig.GetComponent<Animator>() ?? rig.GetComponentInParent<Animator>();
                if (animator != null) animator.Rebind();
                log.LogInfo($"Actor {Path(rig)}: converted to human ({(female ? "female" : "male")}).");
            }
            return changed;
        }

        private static string BodyKind(string rendererName, ActorSwapData data)
        {
            if (!rendererName.StartsWith("mesh_", StringComparison.OrdinalIgnoreCase)) return null;
            foreach (var kind in data.Bodies.Keys)
            {
                if (rendererName.IndexOf(kind, StringComparison.OrdinalIgnoreCase) >= 0) return kind;
            }
            return null;
        }

        private static bool IsFemale(Transform rig, List<SkinnedMeshRenderer> stockHeads)
        {
            // The actor root's ShowRandomMeshByKerbalType decided the type during Instantiate (CIRCLE = female assets).
            var picker = rig.parent != null ? rig.parent.GetComponent<ShowRandomMeshByKerbalType>() : null;
            if (picker != null && picker.chosenType != KerbalType.BUILDER) return picker.chosenType == KerbalType.CIRCLE;
            var active = stockHeads.FirstOrDefault(h => h.gameObject.activeSelf);
            if (active != null) return active.name.IndexOf("female", StringComparison.OrdinalIgnoreCase) >= 0;
            return UnityEngine.Random.value > 0.5f;
        }

        private static GameObject PickPrefab(List<string> keys)
        {
            if (keys == null || keys.Count == 0) return null;
            var available = keys.Select(Prefab).Where(p => p != null).ToList();
            if (available.Count == 0) return null;
            return available[UnityEngine.Random.Range(0, available.Count)];
        }

        /// Instantiates a human body/head prefab, binds its SkinnedMeshRenderers to the actor's bones and
        /// moves its rigid meshes (backpack) under the same-named bones. Returns false, adding nothing, when
        /// a bone the mesh needs is missing from the actor rig.
        private static bool AddSkinned(GameObject prefab, Transform rig, Transform master, Dictionary<string, Transform> bones, int layer)
        {
            var inst = UnityEngine.Object.Instantiate(prefab);
            inst.name = prefab.name;
            var renderers = inst.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            foreach (var smr in renderers)
            {
                var newBones = new Transform[smr.bones.Length];
                for (var i = 0; i < smr.bones.Length; i++)
                {
                    var b = smr.bones[i];
                    if (b == null || !bones.TryGetValue(b.name, out newBones[i]))
                    {
                        HumanKerbalsPlugin.Instance.SWLogger.LogWarning(
                            $"Actor {Path(rig)}: bone '{(b ? b.name : "null")}' needed by {prefab.name}/{smr.name} is missing, part skipped.");
                        UnityEngine.Object.Destroy(inst);
                        return false;
                    }
                }
                smr.bones = newBones;
                smr.rootBone = smr.rootBone != null && bones.TryGetValue(smr.rootBone.name, out var root) ? root : master;
            }
            foreach (var smr in renderers)
            {
                smr.transform.SetParent(rig, false);
                smr.transform.localPosition = Vector3.zero;
                smr.transform.localRotation = Quaternion.identity;
                smr.transform.localScale = Vector3.one;
                SetLayer(smr.gameObject, layer);
            }
            foreach (var mr in inst.GetComponentsInChildren<MeshRenderer>(true))
            {
                var parentName = mr.transform.parent != null ? mr.transform.parent.name : null;
                var target = parentName != null && bones.TryGetValue(parentName, out var bone) ? bone : rig;
                mr.transform.SetParent(target, false);
                SetLayer(mr.gameObject, layer);
            }
            UnityEngine.Object.Destroy(inst);
            return true;
        }

        /// Eyes: every MeshRenderer goes under the actor bone named like its prefab parent (local transform kept).
        private static void AddReparented(GameObject prefab, Dictionary<string, Transform> bones, int layer)
        {
            var inst = UnityEngine.Object.Instantiate(prefab);
            foreach (var mr in inst.GetComponentsInChildren<MeshRenderer>(true))
            {
                var parentName = mr.transform.parent != null ? mr.transform.parent.name : "bone_kerbal_master_parent";
                if (bones.TryGetValue(parentName, out var bone))
                {
                    mr.transform.SetParent(bone, false);
                    SetLayer(mr.gameObject, layer);
                }
                else
                {
                    HumanKerbalsPlugin.Instance.SWLogger.LogWarning($"{prefab.name}/{mr.name}: attach bone '{parentName}' not found on the actor.");
                }
            }
            UnityEngine.Object.Destroy(inst);
        }

        /// Hair/helmet: the prefab root is parented to the bone with identity local transform (AttachToNamedParent).
        private static void Attach(GameObject prefab, Transform bone, int layer)
        {
            var inst = UnityEngine.Object.Instantiate(prefab, bone, false);
            inst.name = prefab.name;
            inst.transform.localPosition = Vector3.zero;
            inst.transform.localRotation = Quaternion.identity;
            inst.transform.localScale = Vector3.one;
            SetLayer(inst, layer);
        }

        private static void SetLayer(GameObject go, int layer)
        {
            foreach (var t in go.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = layer;
        }

        private static Transform FindDeep(Transform t, string name)
        {
            if (t.name == name) return t;
            for (var i = 0; i < t.childCount; i++)
            {
                var r = FindDeep(t.GetChild(i), name);
                if (r != null) return r;
            }
            return null;
        }

        private static string Path(Transform t)
        {
            var parts = new List<string>();
            while (t != null)
            {
                parts.Add(t.name);
                t = t.parent;
            }
            parts.Reverse();
            return string.Join("/", parts);
        }
    }
}
