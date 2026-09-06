"""Export hand-modelled human parts from blender/human_rig.blend as Unity-ready FBX files.

Usage (headless, from the project root):
    blender --background blender/human_rig.blend --python tools/blender_export_parts.py -- unity/Assets/HumanKerbals/Models

Contract (the same one tools/blender_make_human.py follows):
  * the armature is "kerbal_rig" (built by tools/blender_build_rig.py, do not re-create it);
  * skinned parts (suit, heads) are children of the armature with an Armature modifier and vertex
    groups named after bones, placed with `finalize()` (matrix_world = A, data in armature space);
  * eye balls/lids and the backpack are bone-parented (`parent_to_bone`);
  * helmet and hair meshes are attached parts exported in bone-local space.

Object names decide the export file:
  mesh_body_human_<suit>_NN, mesh_backpack_human_NN  -> body_human_<suit>_NN.fbx
  mesh_head_human_<m|f>_NN                           -> head_human_<m|f>_NN.fbx
  mesh_eye_human_<m|f>_ball_<l|r>, mesh_eyelid_human_<m|f>_<l|r><u|d> -> eyes_human_<m|f>_NN.fbx
  mesh_helmet_human_NN*                              -> helm_human_spacesuit_NN.fbx
  hairstyle_human_<m|f>_NN                           -> hair_human_<m|f>_NN.fbx
"""
import os
import re
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blender_make_human import export_with_rig, export_attached  # noqa: E402

ARM_NAME = "kerbal_rig"


def main():
    out_dir = os.path.abspath(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else "unity/Assets/HumanKerbals/Models"
    os.makedirs(out_dir, exist_ok=True)
    arm = bpy.data.objects[ARM_NAME]
    human = bpy.data.collections.get("human")
    objs = [o for o in (human.objects if human else bpy.data.objects) if o.type == "MESH"]

    groups = {}
    for o in objs:
        n = o.name
        m = re.match(r"mesh_body_human_(\w+?_\d+)$", n) or re.match(r"mesh_backpack_human_(\d+)$", n)
        if n.startswith("mesh_body_human_") or n.startswith("mesh_backpack_human_"):
            suit = re.search(r"mesh_body_human_(\w+)$", n)
            key = "body_human_" + (suit.group(1) if suit else "spacesuit_01")
            groups.setdefault(("rig", key), []).append(o)
        elif n.startswith("mesh_head_human_"):
            groups.setdefault(("rig", "head_human_" + n[len("mesh_head_human_"):]), []).append(o)
        elif n.startswith("mesh_eye_human_") or n.startswith("mesh_eyelid_human_"):
            tag = re.search(r"_human_([mf])_", n).group(1)
            groups.setdefault(("rig", f"eyes_human_{tag}_01"), []).append(o)
        elif n.startswith("mesh_helmet_human_"):
            num = re.search(r"mesh_helmet_human_(\d+)", n).group(1)
            groups.setdefault(("attach:bone_kerbal_helmet", f"helm_human_spacesuit_{num}"), []).append(o)
        elif n.startswith("hairstyle_human_"):
            groups.setdefault(("attach:bone_kerbal_head", "hair_human_" + n[len("hairstyle_human_"):]), []).append(o)

    # Backpack belongs with the suit it was authored for.
    backpacks = [o for o in objs if o.name.startswith("mesh_backpack_human_")]
    for (kind, stem), members in list(groups.items()):
        if kind == "rig" and stem.startswith("body_human_"):
            for bp in backpacks:
                if bp not in members:
                    members.append(bp)
    for (kind, stem), members in groups.items():
        if stem.startswith("body_human_") and all(m.name.startswith("mesh_backpack_human_") for m in members):
            continue
        if kind == "rig":
            export_with_rig(arm, stem, members, out_dir)
        else:
            export_attached(arm, stem, members, kind.split(":", 1)[1], out_dir)


if __name__ == "__main__":
    main()
