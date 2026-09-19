using System.Linq;
using HarmonyLib;
using KSP.Game;
using UnityEngine;

namespace HumbleSpaceProgram
{
    // The shared rig is Z-up, and neck_ach's local Z follows the spine. Resize bones rather
    // than individual meshes so skinning, eyes, hair and helmets remain attached together.
    [DefaultExecutionOrder(10000)]
    public sealed class HumanSize : MonoBehaviour
    {
        private Transform _master;
        private Transform _neck;
        private Vector3 _masterScale;
        private Vector3 _neckScale;

        public static void Apply(Transform master)
        {
            Configure(master, 1f);
        }

        public static void ApplyFramed(Transform master)
        {
            // Preserve the 65 cm envelope expected by stock IVA seats and photo-booth cameras,
            // while giving these representations the same body/head proportions as world humans.
            Configure(master, 0.375f);
        }

        private static void Configure(Transform master, float frameScale)
        {
            if (master == null || master.GetComponent<HumanSize>() != null) return;
            var component = master.gameObject.AddComponent<HumanSize>();
            component._master = master;
            component._neck = master.GetComponentsInChildren<Transform>(true)
                .FirstOrDefault(t => t.name == "bone_kerbal_neck_ach");
            component._masterScale = Vector3.Scale(master.localScale, new Vector3(2.2f, 2.2f, 4.2f) * frameScale);
            if (component._neck != null)
                component._neckScale = Vector3.Scale(component._neck.localScale, new Vector3(0.44f, 0.44f, 0.23f));
            component.LateUpdate();
            // Stock culling bounds describe the short rig. Keep animated bounds current for the
            // taller meshes so heads and limbs do not vanish at the edge of the camera view.
            if (master.parent != null)
                foreach (var renderer in master.parent.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                    renderer.updateWhenOffscreen = true;
        }

        private void LateUpdate()
        {
            if (_master != null) _master.localScale = _masterScale;
            if (_neck != null) _neck.localScale = _neckScale;
        }
    }

    [HarmonyPatch(typeof(Kerbal3DModel), "BuildCharacterFromLoadedAttributes")]
    internal static class HumanRosterSizePatch
    {
        [HarmonyPostfix]
        private static void Postfix(Kerbal3DModel __instance)
        {
            // The photo booth's model prefab is flagged as EVA, but its camera is fixed at kerbal
            // head height, so portraits need the framed size like IVA seats do.
            var framed = !__instance.IsEVAKerbal ||
                         __instance.GetComponentInParent<KerbalPhotoBooth>(true) != null;
            foreach (var master in __instance.GetComponentsInChildren<Transform>(true)
                         .Where(t => t.name == "bone_kerbal_master_parent" &&
                                     t.parent != null && t.parent.name.StartsWith("body_human_")))
            {
                if (framed) HumanSize.ApplyFramed(master);
                else HumanSize.Apply(master);
            }
        }
    }
}
