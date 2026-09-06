"""Build the kerbal armature and import the stock reference meshes into a fresh Blender scene.

Usage (headless):
    blender --background --python tools/blender_build_rig.py -- reference blender/kerbal_rig.blend

Coordinate conventions (verified against the game, see docs/game-reference.md "FBX round trip"):
  * Scene frame C: Blender (x, y, z) = Unity (-x, -z, y). Z-up, the character faces -Y. Every
    position authored in Blender (this script and blender_make_human.py) uses this frame.
  * Blender's FBX exporter (default -Z forward / Y up) rotates ROOT nodes by -90 deg about X and writes
    child transforms untouched; Unity's importer then mirrors X on every node. Hence:
      - the armature object is rotated A = +90 deg about X so its exported root transform is identity,
      - bone matrices in armature space are the stock Unity matrices conjugated by the X mirror,
      - mesh objects under the armature get matrix_world = A and their vertex data transformed by A^-1.
    With that the imported bone transforms equal the stock ones exactly (tools/compare_rig.py).
"""
import json
import os
import sys

import bpy
from mathutils import Quaternion, Vector, Matrix

DEFAULT_ARGS = ["reference", "blender/kerbal_rig.blend"]
BODY_HIERARCHY = "body_spacesuit_01"
MESHES = [
    ("mesh_spacesuit_01", "body_spacesuit_01", None),
    ("mesh_spacesuit_01_hardware", "body_spacesuit_01", None),
    ("mesh_backpack_01", "body_spacesuit_01", None),
    ("mesh_male_head_01", "head_m_01", None),
    ("mesh_female_head_01", "head_f_01", None),
    ("mesh_eye_m_ball_l_original", "eyes_m_01", None),
    ("mesh_eye_m_ball_r_original", "eyes_m_01", None),
    ("mesh_eyelid_m_lu_original", "eyes_m_01", None),
    ("mesh_eyelid_m_ld_original", "eyes_m_01", None),
    ("mesh_eyelid_m_ru_original", "eyes_m_01", None),
    ("mesh_eyelid_m_rd_original", "eyes_m_01", None),
    ("mesh_helmet_01", "helm_spacesuit_01", "bone_kerbal_helmet"),
    ("mesh_helmet_01_visor", "helm_spacesuit_01", "bone_kerbal_helmet"),
    ("mesh_spacesuit_01_helmetbase", "helm_spacesuit_01", "bone_kerbal_helmet"),
    ("mesh_facialhair_fullbeard", "facialhair_fullbeard", None),
]
DEFAULT_BONE_LENGTH = 0.02
ARMATURE_NAME = "kerbal_rig"

MIRROR = Matrix.Diagonal((-1, 1, 1, 1))
C = Matrix(((-1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # Unity -> scene
C_INV = C.inverted()
A = Matrix.Rotation(1.5707963267948966, 4, "X")                           # armature object rotation
A_INV = A.inverted()


def matrix_from_local(node):
    pos = Vector(node["localPosition"])
    x, y, z, w = node["localRotation"]
    rot = Quaternion((w, x, y, z))
    scale = Vector(node["localScale"])
    return Matrix.LocRotScale(pos, rot, scale)


def collect_world_matrices(node, parent_world, out):
    world = parent_world @ matrix_from_local(node)
    out.setdefault(node["name"], world)
    for child in node.get("children", []):
        collect_world_matrices(child, world, out)


def load_hierarchy(ref_dir, name):
    """Unity world matrices relative to the prefab root (the root's own transform is discarded: the
    game re-parents these prefabs with identity local transforms)."""
    path = os.path.join(ref_dir, "hierarchies", name + ".json")
    if not os.path.exists(path):
        return None, {}
    roots = json.load(open(path))
    worlds = {}
    for root in roots:
        worlds[root["name"]] = Matrix.Identity(4)
        for child in root.get("children", []):
            collect_world_matrices(child, Matrix.Identity(4), worlds)
    return roots[0], worlds


def to_scene(m):
    return C @ m @ C_INV


def unity_to_armature(m):
    return MIRROR @ m @ MIRROR


def build_armature(root_node, worlds):
    arm_data = bpy.data.armatures.new(ARMATURE_NAME)
    arm_obj = bpy.data.objects.new(ARMATURE_NAME, arm_data)
    bpy.context.collection.objects.link(arm_obj)
    arm_obj.matrix_world = A
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")

    def add_bone(node, parent_bone):
        name = node["name"]
        if not name.startswith("bone_"):
            for child in node.get("children", []):
                add_bone(child, parent_bone)
            return
        mat = unity_to_armature(worlds[name])
        child_bones = [c for c in node.get("children", []) if c["name"].startswith("bone_")]
        length = DEFAULT_BONE_LENGTH
        if child_bones:
            d = (unity_to_armature(worlds[child_bones[0]["name"]]).to_translation() - mat.to_translation()).length
            if d > 1e-4:
                length = d
        bone = arm_data.edit_bones.new(name)
        bone.head = Vector((0, 0, 0))
        bone.tail = Vector((0, length, 0))
        loc, rot, _scale = mat.decompose()
        bone.matrix = Matrix.LocRotScale(loc, rot, Vector((1, 1, 1)))
        bone.parent = parent_bone
        bone.use_connect = False
        for child in node.get("children", []):
            add_bone(child, bone)

    add_bone(root_node, None)
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_obj


def import_meshes(ref_dir, body_worlds):
    imported = []
    hier_cache = {}
    for name, hier_name, attach_bone in MESHES:
        path = os.path.join(ref_dir, "meshes", name + ".obj")
        if not os.path.exists(path):
            print("missing", path)
            continue
        if hier_name not in hier_cache:
            hier_cache[hier_name] = load_hierarchy(ref_dir, hier_name)[1]
        node_worlds = hier_cache[hier_name]
        world_u = node_worlds.get(name, Matrix.Identity(4))
        if attach_bone and attach_bone in body_worlds:
            world_u = body_worlds[attach_bone] @ world_u
        before = set(bpy.data.objects)
        # UnityPy writes (-x, y, z) of Unity mesh space; the importer with -Z forward / Y up stores the
        # axis conversion in the object matrix, which composed with that X negation equals C.
        bpy.ops.wm.obj_import(filepath=path, forward_axis="NEGATIVE_Z", up_axis="Y")
        for obj in set(bpy.data.objects) - before:
            obj.name = name
            importer_matrix = obj.matrix_world.copy()
            obj.matrix_world = to_scene(world_u) @ importer_matrix
            imported.append(obj)
    return imported


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else DEFAULT_ARGS
    ref_dir, out_blend = argv[0], argv[1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body_root, body_worlds = load_hierarchy(ref_dir, BODY_HIERARCHY)
    arm = build_armature(body_root, body_worlds)
    meshes = import_meshes(ref_dir, body_worlds)
    ref = bpy.data.collections.new("stock_reference")
    bpy.context.scene.collection.children.link(ref)
    for obj in meshes:
        bpy.context.scene.collection.objects.unlink(obj)
        ref.objects.link(obj)
    os.makedirs(os.path.dirname(os.path.abspath(out_blend)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_blend))
    print(f"saved {out_blend}: {len(arm.data.bones)} bones, {len(meshes)} reference meshes")


if __name__ == "__main__":
    main()
