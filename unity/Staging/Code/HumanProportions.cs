// Optional runtime component for Phase 3 (human body proportions).
//
// The stock animation clips bake local POSITION curves for a subset of bones (knees, shoulders,
// elbows, hands, neck, eyes, jaw, jetpack arms, root; see docs/game-reference.md, "Animated position
// bones"). Because the rig is a Generic (non-humanoid) avatar, any human-proportioned skeleton would
// have those bones snapped back to kerbal offsets every frame by the Animator.
//
// This component re-applies the human bind offsets in LateUpdate for the bones whose stock curves are
// constant or nearly constant. Bones with genuinely animated translation (root, jetpack joysticks,
// eyes/eyelids, jaw) are left alone. It is a stop-gap: the clean solution is retargeting the clips
// (Phase 3b), after which this component becomes unnecessary.
//
// Attach it to the body_* prefab root (the object that owns bone_kerbal_master_parent) and fill
// `offsets` with the human local positions measured in Blender.

using System;
using System.Collections.Generic;
using UnityEngine;

namespace HumbleSpaceProgram
{
    public sealed class HumanProportions : MonoBehaviour
    {
        [Serializable]
        public struct BoneOffset
        {
            public string boneName;
            public Vector3 localPosition;
        }

        public BoneOffset[] offsets = Array.Empty<BoneOffset>();

        private readonly List<(Transform bone, Vector3 pos)> _resolved = new List<(Transform, Vector3)>();

        private void Start()
        {
            var byName = new Dictionary<string, Transform>();
            foreach (var t in GetComponentsInChildren<Transform>(true))
            {
                if (!byName.ContainsKey(t.name)) byName[t.name] = t;
            }
            foreach (var o in offsets)
            {
                if (byName.TryGetValue(o.boneName, out var bone)) _resolved.Add((bone, o.localPosition));
            }
        }

        private void LateUpdate()
        {
            for (var i = 0; i < _resolved.Count; i++)
            {
                _resolved[i].bone.localPosition = _resolved[i].pos;
            }
        }
    }
}
