"""Generate the Phase 1 stylized human parts on the kerbal rig and export them as FBX.

Usage (headless, from the project root):
    blender --background blender/kerbal_rig.blend --python tools/blender_make_human.py -- unity/Assets/HumbleSpaceProgram/Models blender/human_rig.blend

Builds (all procedurally, no stock geometry is reused):
  * body_human_spacesuit_01  skinned suit: pelvis, torso, neck, arms, gloves, legs, boots + backpack under bone_kerbal_eva_root
  * body_human_jumpsuit_01 / body_human_scientist_01  same limbs in civilian clothes (orange jumpsuit; white lab coat
    over grey trousers), bare hands and neck, no backpack (colonists, KSC staff and the Mission Control actors)
  * head_human_m_01 / _f_01  skinned head with chin, nose, ears, brows, mouth (bone_kerbal_head, jaw region on bone_kerbal_jaw_d)
  * eyes_human_m_01 / _f_01  eyeballs with iris and upper/lower lids parented to the eye/lid bones
  * helm_human_spacesuit_01  helmet shell + visor + neck ring in bone_kerbal_helmet space
  * hair_human_m_01/_m_02/_f_01/_f_02  hair caps in bone_kerbal_head space

Every skinned/bone-parented FBX carries the whole armature renamed to the part key, which is what
the game's re-skin/re-parent code expects (bones are matched by name).
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

ARM_NAME = "kerbal_rig"
DEFAULT_ARGS = ["unity/Assets/HumbleSpaceProgram/Models", "blender/human_rig.blend"]

# Frame conventions: see tools/blender_build_rig.py. Geometry is authored in the scene frame (Z-up,
# character faces -Y); when a mesh is attached under the armature its data is moved into armature
# space (A^-1) and the object gets matrix_world = A, which is what the FBX round trip expects.
A = Matrix.Rotation(1.5707963267948966, 4, "X")
A_INV = A.inverted()


# Bone anchor points in the scene frame, read from the rig at runtime.
def bone_head(arm, name):
    return arm.matrix_world @ arm.data.bones[name].head_local


def finalize(obj, arm):
    """Move authored (scene-frame) mesh data into armature space and place the object at A."""
    obj.data.transform(A_INV)
    obj.matrix_world = A
    obj.parent = arm
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = Matrix.Identity(4)


# ---------------------------------------------------------------- materials
MATERIALS = {}


def material(name, rgba, roughness=0.6, metallic=0.0):
    if name in MATERIALS:
        return MATERIALS[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if rgba[3] < 1.0:
            bsdf.inputs["Alpha"].default_value = rgba[3]
    mat.diffuse_color = rgba
    mat.roughness = roughness
    mat.metallic = metallic
    if rgba[3] < 1.0:
        mat.surface_render_method = "BLENDED"
    MATERIALS[name] = mat
    return mat


SKIN = (0.87, 0.66, 0.52, 1.0)
SKIN_F = (0.90, 0.72, 0.60, 1.0)
HAIR_BROWN = (0.20, 0.12, 0.07, 1.0)
HAIR_BLOND = (0.75, 0.60, 0.32, 1.0)
HAIR_BLACK = (0.08, 0.07, 0.07, 1.0)
HAIR_RED = (0.45, 0.18, 0.08, 1.0)
SUIT_WHITE = (0.92, 0.92, 0.94, 1.0)
SUIT_GREY = (0.45, 0.47, 0.50, 1.0)
SUIT_ORANGE = (0.95, 0.45, 0.10, 1.0)
BOOT = (0.18, 0.18, 0.20, 1.0)
EYE_WHITE = (0.95, 0.95, 0.95, 1.0)
IRIS_BLUE = (0.16, 0.30, 0.50, 1.0)
IRIS_BROWN = (0.30, 0.18, 0.10, 1.0)
PUPIL = (0.02, 0.02, 0.02, 1.0)
MOUTH = (0.55, 0.25, 0.25, 1.0)
VISOR = (0.55, 0.75, 0.95, 0.35)
COAT_WHITE = (0.95, 0.95, 0.96, 1.0)
TROUSER_GREY = (0.28, 0.30, 0.34, 1.0)
SHIRT_BLUE = (0.55, 0.70, 0.90, 1.0)
TIE_RED = (0.50, 0.12, 0.12, 1.0)
SHOE_BLACK = (0.08, 0.08, 0.09, 1.0)


# ---------------------------------------------------------------- bmesh helpers
class Builder:
    """Accumulates primitives into one mesh with per-piece vertex group (bone) and material."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.deform = self.bm.verts.layers.deform.verify()
        self.groups = []     # bone names in vertex-group order
        self.materials = []  # materials in slot order

    def _group_index(self, bone):
        if bone is None:
            return None
        if bone not in self.groups:
            self.groups.append(bone)
        return self.groups.index(bone)

    def _material_index(self, mat):
        if mat not in self.materials:
            self.materials.append(mat)
        return self.materials.index(mat)

    def add(self, piece_bm, bone, mat, weights=None):
        """Append piece geometry. weights: optional callable(vert_co) -> {bone: w} overriding `bone`."""
        gi = self._group_index(bone)
        mi = self._material_index(mat)
        tmp = bpy.data.meshes.new("tmp_piece")
        piece_bm.to_mesh(tmp)
        piece_bm.free()
        nv = len(self.bm.verts)
        nf = len(self.bm.faces)
        self.bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
        self.bm.verts.ensure_lookup_table()
        self.bm.faces.ensure_lookup_table()
        for v in self.bm.verts[nv:]:
            if weights is not None:
                for b, w in weights(v.co).items():
                    v[self.deform][self._group_index(b)] = w
            elif gi is not None:
                v[self.deform][gi] = 1.0
        for f in self.bm.faces[nf:]:
            f.material_index = mi
            f.smooth = True

    def build(self, collection, arm=None, skinned=True):
        mesh = bpy.data.meshes.new(self.name)
        obj = bpy.data.objects.new(self.name, mesh)
        collection.objects.link(obj)
        for bone in self.groups:
            obj.vertex_groups.new(name=bone)
        bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=1e-6)
        self.bm.to_mesh(mesh)
        self.bm.free()
        for mat in self.materials:
            mesh.materials.append(mat)
        for p in mesh.polygons:
            p.use_smooth = True
        if arm is not None:
            finalize(obj, arm)
        if skinned and arm is not None:
            mod = obj.modifiers.new("Armature", "ARMATURE")
            mod.object = arm
        return obj


def sphere(center, radii, segments=24, rings=16):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1.0)
    m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal((radii[0], radii[1], radii[2], 1.0))
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    return bm


def sphere_shaped(center, radii, shape_fn, segments=32, rings=24):
    """Sphere whose vertices are remapped by shape_fn(unit_vector) -> unit_vector-ish."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1.0)
    for v in bm.verts:
        v.co = shape_fn(v.co.copy())
    m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal((radii[0], radii[1], radii[2], 1.0))
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    return bm


def cylinder(p0, p1, r0, r1, segments=16):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    length = d.length
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=r0, radius2=r1, depth=length)
    rot = d.normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()
    m = Matrix.Translation((p0 + p1) / 2) @ rot
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    return bm


def box(center, size):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    bmesh.ops.bevel(bm, geom=bm.verts[:] + bm.edges[:], offset=min(size) * 0.15, segments=2, affect="EDGES")
    return bm


def torus(center, major, minor, segments=24, rings=10):
    bm = bmesh.new()
    verts = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        ring = []
        for j in range(rings):
            b = 2 * math.pi * j / rings
            x = (major + minor * math.cos(b)) * math.cos(a)
            y = (major + minor * math.cos(b)) * math.sin(a)
            z = minor * math.sin(b)
            ring.append(bm.verts.new((x, y, z)))
        verts.append(ring)
    for i in range(segments):
        for j in range(rings):
            a, b = verts[i][j], verts[(i + 1) % segments][j]
            c, d = verts[(i + 1) % segments][(j + 1) % rings], verts[i][(j + 1) % rings]
            bm.faces.new((a, b, c, d))
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(center)), verts=bm.verts)
    return bm


def keep_verts(bm, predicate):
    doomed = [v for v in bm.verts if not predicate(v.co)]
    bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    return bm


def cut(bm, point, normal, keep="front"):
    """Slice the mesh with a plane and keep one side (clean boundary). keep='front' keeps the side the
    normal points to."""
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=Vector(point), plane_no=Vector(normal).normalized(),
                           clear_outer=(keep == "back"), clear_inner=(keep == "front"))
    return bm


def mirror_x(p):
    return (-p[0], p[1], p[2])


# ---------------------------------------------------------------- parts
def build_suit(arm, col):
    b = Builder("mesh_body_human_spacesuit_01")
    suit = material("HumanSuit", SUIT_WHITE, 0.55)
    grey = material("HumanSuitGrey", SUIT_GREY, 0.5)
    orange = material("HumanSuitOrange", SUIT_ORANGE, 0.5)
    boot = material("HumanBoot", BOOT, 0.7)

    pelvis = bone_head(arm, "bone_kerbal_pelvis")
    spine_u = bone_head(arm, "bone_kerbal_spine_upper")
    neck = bone_head(arm, "bone_kerbal_neck")
    head = bone_head(arm, "bone_kerbal_head")

    # Torso: lower part to spine_lower, upper part to spine_upper (smooth split at spine_upper height).
    def torso_weights(co):
        t = (co.z - (spine_u.z - 0.02)) / 0.04
        t = max(0.0, min(1.0, t))
        return {"bone_kerbal_spine_lower": 1.0 - t, "bone_kerbal_spine_upper": t}

    torso = cylinder((0, 0.005, pelvis.z - 0.005), (0, 0.0, neck.z + 0.005), 0.095, 0.11, segments=24)
    bmesh.ops.transform(torso, matrix=Matrix.Diagonal((1.0, 0.78, 1.0, 1.0)), verts=torso.verts)
    b.add(torso, None, suit, weights=torso_weights)
    # Chest panel (orange accent) and belly life-support box.
    b.add(box((0, -0.075, spine_u.z + 0.02), (0.09, 0.02, 0.05)), "bone_kerbal_spine_upper", orange)
    b.add(box((0, -0.07, pelvis.z + 0.015), (0.10, 0.03, 0.045)), "bone_kerbal_spine_lower", grey)
    # Pelvis / hips.
    b.add(sphere((0, 0.0, pelvis.z - 0.01), (0.105, 0.085, 0.06)), "bone_kerbal_pelvis", suit)
    # Neck.
    b.add(cylinder((0, -0.01, neck.z - 0.01), (0, -0.012, head.z + 0.01), 0.036, 0.034), "bone_kerbal_neck", grey)

    for side in ("l", "r"):
        sh = bone_head(arm, f"bone_kerbal_{side}_shoulder")
        el = bone_head(arm, f"bone_kerbal_{side}_elbow")
        ha = bone_head(arm, f"bone_kerbal_{side}_hand")
        tip = bone_head(arm, f"bone_kerbal_{side}_middle_03")
        th = bone_head(arm, f"bone_kerbal_{side}_thigh")
        kn = bone_head(arm, f"bone_kerbal_{side}_knee")
        ft = bone_head(arm, f"bone_kerbal_{side}_foot")
        toe = bone_head(arm, f"bone_kerbal_{side}_toe")
        sgn = 1 if side == "l" else -1

        b.add(sphere(sh, (0.042, 0.042, 0.042)), f"bone_kerbal_{side}_shoulder", suit)
        b.add(cylinder(sh, el, 0.036, 0.031), f"bone_kerbal_{side}_shoulder", suit)
        b.add(sphere(el, (0.032, 0.032, 0.032)), f"bone_kerbal_{side}_elbow", suit)
        b.add(cylinder(el, ha, 0.031, 0.028), f"bone_kerbal_{side}_elbow", suit)
        b.add(torus(ha, 0.03, 0.008), f"bone_kerbal_{side}_hand", grey)  # glove ring
        glove_center = (ha + tip) / 2 + Vector((sgn * 0.005, 0.0, -0.002))
        b.add(sphere(glove_center, (0.06, 0.04, 0.03)), f"bone_kerbal_{side}_hand", suit)
        thumb = ha + Vector((sgn * 0.035, -0.035, -0.005))
        b.add(sphere(thumb, (0.02, 0.028, 0.016)), f"bone_kerbal_{side}_hand", suit)

        b.add(sphere(th + Vector((0, 0, 0.005)), (0.05, 0.05, 0.045)), f"bone_kerbal_{side}_thigh", suit)
        b.add(cylinder(th, kn, 0.046, 0.04), f"bone_kerbal_{side}_thigh", suit)
        b.add(sphere(kn, (0.04, 0.04, 0.04)), f"bone_kerbal_{side}_knee", suit)
        b.add(cylinder(kn, ft + Vector((0, 0, 0.01)), 0.04, 0.038), f"bone_kerbal_{side}_knee", suit)
        b.add(torus(ft + Vector((0, 0, 0.012)), 0.038, 0.01), f"bone_kerbal_{side}_foot", grey)
        boot_center = Vector((ft.x, (ft.y + toe.y) / 2 - 0.01, 0.028))
        b.add(box(boot_center, (0.085, 0.14, 0.056)), f"bone_kerbal_{side}_foot", boot)

    suit_obj = b.build(col, arm, skinned=True)

    # Backpack: rigid mesh under bone_kerbal_eva_root (jetpack root), like the stock body prefab.
    bp = Builder("mesh_backpack_human_01")
    eva = bone_head(arm, "bone_kerbal_eva_root")
    bp.add(box((0, eva.y + 0.055, eva.z - 0.02), (0.19, 0.10, 0.22)), None, material("HumanBackpack", SUIT_GREY, 0.5))
    bp.add(cylinder((-0.055, eva.y + 0.11, eva.z - 0.12), (-0.055, eva.y + 0.11, eva.z + 0.08), 0.02, 0.02, 12), None, material("HumanTank", SUIT_WHITE, 0.4))
    bp.add(cylinder((0.055, eva.y + 0.11, eva.z - 0.12), (0.055, eva.y + 0.11, eva.z + 0.08), 0.02, 0.02, 12), None, material("HumanTank", SUIT_WHITE, 0.4))
    bp_obj = bp.build(col, arm, skinned=False)
    parent_to_bone(bp_obj, arm, "bone_kerbal_eva_root")
    return suit_obj, bp_obj


def build_civilian_body(arm, col, variant):
    """Jumpsuit or lab-coat body: the suit's limb layout in civilian clothes, bare hands/neck, no backpack.
    variant: "jumpsuit" (orange coverall, grey cuffs, dark boots) or "scientist" (white coat over grey
    trousers, blue shirt collar and tie, black shoes)."""
    b = Builder(f"mesh_body_human_{variant}_01")
    skin = material("HumanSkinM", SKIN, 0.55)
    if variant == "scientist":
        top = material("HumanLabCoat", COAT_WHITE, 0.65)
        trousers = material("HumanTrousers", TROUSER_GREY, 0.75)
        shoes = material("HumanShoe", SHOE_BLACK, 0.45)
        cuff = top
        collar = material("HumanShirt", SHIRT_BLUE, 0.6)
    else:
        top = material("HumanJumpsuit", SUIT_ORANGE, 0.65)
        trousers = top
        shoes = material("HumanBoot", BOOT, 0.7)
        cuff = material("HumanSuitGrey", SUIT_GREY, 0.5)
        collar = cuff

    pelvis = bone_head(arm, "bone_kerbal_pelvis")
    spine_u = bone_head(arm, "bone_kerbal_spine_upper")
    neck = bone_head(arm, "bone_kerbal_neck")
    head = bone_head(arm, "bone_kerbal_head")

    def torso_weights(co):
        t = (co.z - (spine_u.z - 0.02)) / 0.04
        t = max(0.0, min(1.0, t))
        return {"bone_kerbal_spine_lower": 1.0 - t, "bone_kerbal_spine_upper": t}

    wide = 1.06 if variant == "scientist" else 1.0
    torso = cylinder((0, 0.005, pelvis.z - 0.005), (0, 0.0, neck.z + 0.005), 0.092 * wide, 0.106 * wide, segments=24)
    bmesh.ops.transform(torso, matrix=Matrix.Diagonal((1.0, 0.78, 1.0, 1.0)), verts=torso.verts)
    b.add(torso, None, top, weights=torso_weights)
    # Collar (shirt / suit collar) just under the neck, and the front placket.
    b.add(torus((0, -0.004, neck.z - 0.004), 0.05, 0.012, 24, 8), "bone_kerbal_spine_upper", collar)
    if variant == "scientist":
        b.add(box((0, -0.088, spine_u.z + 0.03), (0.05, 0.012, 0.06)), "bone_kerbal_spine_upper", collar)   # shirt front
        b.add(box((0, -0.094, spine_u.z + 0.005), (0.016, 0.008, 0.09)), "bone_kerbal_spine_upper", material("HumanTie", TIE_RED, 0.6))
        # Coat hem: a short flare below the hips.
        hem = cylinder((0, 0.003, pelvis.z + 0.005), (0, 0.003, pelvis.z - 0.075), 0.108, 0.118, segments=24)
        bmesh.ops.transform(hem, matrix=Matrix.Diagonal((1.0, 0.8, 1.0, 1.0)), verts=hem.verts)
        b.add(hem, "bone_kerbal_pelvis", top)
    else:
        b.add(box((0, -0.082, spine_u.z + 0.02), (0.05, 0.012, 0.035)), "bone_kerbal_spine_upper", cuff)     # chest pocket / badge
        b.add(torus((0, 0.0, pelvis.z + 0.012), 0.098, 0.012, 24, 8), "bone_kerbal_pelvis", cuff)             # belt
    b.add(sphere((0, 0.0, pelvis.z - 0.01), (0.105, 0.085, 0.06)), "bone_kerbal_pelvis", trousers)
    b.add(cylinder((0, -0.01, neck.z - 0.01), (0, -0.012, head.z + 0.01), 0.034, 0.032), "bone_kerbal_neck", skin)

    for side in ("l", "r"):
        sh = bone_head(arm, f"bone_kerbal_{side}_shoulder")
        el = bone_head(arm, f"bone_kerbal_{side}_elbow")
        ha = bone_head(arm, f"bone_kerbal_{side}_hand")
        tip = bone_head(arm, f"bone_kerbal_{side}_middle_03")
        th = bone_head(arm, f"bone_kerbal_{side}_thigh")
        kn = bone_head(arm, f"bone_kerbal_{side}_knee")
        ft = bone_head(arm, f"bone_kerbal_{side}_foot")
        toe = bone_head(arm, f"bone_kerbal_{side}_toe")
        sgn = 1 if side == "l" else -1

        b.add(sphere(sh, (0.040, 0.040, 0.040)), f"bone_kerbal_{side}_shoulder", top)
        b.add(cylinder(sh, el, 0.034, 0.029), f"bone_kerbal_{side}_shoulder", top)
        b.add(sphere(el, (0.030, 0.030, 0.030)), f"bone_kerbal_{side}_elbow", top)
        b.add(cylinder(el, ha, 0.029, 0.026), f"bone_kerbal_{side}_elbow", top)
        b.add(torus(ha, 0.027, 0.007), f"bone_kerbal_{side}_hand", cuff)  # sleeve cuff
        hand_center = (ha + tip) / 2 + Vector((sgn * 0.004, 0.0, -0.002))
        b.add(sphere(hand_center, (0.052, 0.034, 0.024)), f"bone_kerbal_{side}_hand", skin)
        thumb = ha + Vector((sgn * 0.030, -0.032, -0.004))
        b.add(sphere(thumb, (0.016, 0.024, 0.013)), f"bone_kerbal_{side}_hand", skin)

        b.add(sphere(th + Vector((0, 0, 0.005)), (0.048, 0.048, 0.043)), f"bone_kerbal_{side}_thigh", trousers)
        b.add(cylinder(th, kn, 0.044, 0.038), f"bone_kerbal_{side}_thigh", trousers)
        b.add(sphere(kn, (0.038, 0.038, 0.038)), f"bone_kerbal_{side}_knee", trousers)
        b.add(cylinder(kn, ft + Vector((0, 0, 0.012)), 0.038, 0.034), f"bone_kerbal_{side}_knee", trousers)
        shoe_center = Vector((ft.x, (ft.y + toe.y) / 2 - 0.008, 0.024))
        b.add(box(shoe_center, (0.078, 0.135, 0.048)), f"bone_kerbal_{side}_foot", shoes)

    return b.build(col, arm, skinned=True)


def head_shape(female):
    """Deform a unit sphere into a stylised human head: soft jaw taper, flatter back, full cheeks."""
    def fn(p):
        x, y, z = p.x, p.y, p.z
        if z < 0:
            # jaw taper: gently narrower below the eye line, chin pushed a little forward
            t = (-z) ** 2.0
            x *= 1.0 - (0.30 if not female else 0.34) * t
            y = y * (1.0 - 0.18 * t) - 0.05 * t
        else:
            # rounder cranium
            x *= 1.0 + 0.04 * z
        if y > 0.2:  # flatten the back of the skull a little
            y *= 0.97
        return Vector((x, y, z))
    return fn


def surface_point(center, radii, shape_fn, unit_dir):
    """World position of the shaped head surface in direction unit_dir (unit-sphere coordinates)."""
    p = shape_fn(Vector(unit_dir).normalized())
    return Vector(center) + Vector((p.x * radii[0], p.y * radii[1], p.z * radii[2]))


def build_head(arm, col, female):
    tag = "f" if female else "m"
    b = Builder(f"mesh_head_human_{tag}_01")
    skin = material("HumanSkinF" if female else "HumanSkinM", SKIN_F if female else SKIN, 0.55)
    brow = material("HumanBrow", HAIR_BROWN, 0.8)
    mouth = material("HumanMouth", MOUTH, 0.6)
    head_bone = bone_head(arm, "bone_kerbal_head")
    jaw = bone_head(arm, "bone_kerbal_jaw_d")
    eye = bone_head(arm, "bone_kerbal_l_eye")

    center = Vector((0.0, -0.005, 0.50))
    radii = (0.128, 0.132, 0.150) if not female else (0.122, 0.128, 0.148)

    def head_weights(co):
        # Lower front of the face follows the lower jaw bone so mouth animations move the chin.
        below = jaw.z - co.z
        t = max(0.0, min(1.0, (below - 0.01) / 0.04)) if co.y < 0.0 else 0.0
        return {"bone_kerbal_head": 1.0 - t, "bone_kerbal_jaw_d": t}

    shape = head_shape(female)
    b.add(sphere_shaped(center, radii, shape), None, skin, weights=head_weights)

    def on_face(unit_dir, outward=0.0):
        p = surface_point(center, radii, shape, unit_dir)
        return p + Vector((0.0, -outward, 0.0))

    # Nose: sits on the face surface just below the eye line.
    nose_c = on_face((0.0, -1.0, 0.02), -0.012)
    b.add(sphere(nose_c, (0.018, 0.028, 0.026) if not female else (0.015, 0.024, 0.022), 12, 10), "bone_kerbal_head", skin)
    # Ears
    for sgn in (1, -1):
        b.add(sphere((sgn * (radii[0] - 0.004), 0.0, 0.505), (0.012, 0.026, 0.038), 12, 10), "bone_kerbal_head", skin)
    # Brows, above the eye bones on the surface.
    for sgn in (1, -1):
        ux = sgn * eye.x / radii[0]
        uz = (eye.z + 0.05 - center.z) / radii[2]
        uy = -math.sqrt(max(0.05, 1.0 - ux * ux - uz * uz))
        b.add(sphere(on_face((ux, uy, uz), 0.004), (0.034, 0.010, 0.008), 10, 6), "bone_kerbal_head", brow)
    # Mouth: a thin dark ellipsoid on the surface below the nose, follows the jaw bone.
    mouth_c = on_face((0.0, -1.0, -0.33), 0.002)
    b.add(sphere(mouth_c, (0.034, 0.010, 0.007), 12, 6), "bone_kerbal_jaw_d", mouth)
    return b.build(col, arm, skinned=True)


def build_eyes(arm, col, female):
    tag = "f" if female else "m"
    white = material("HumanEyeWhite", EYE_WHITE, 0.2)
    iris = material("HumanIrisF" if female else "HumanIrisM", IRIS_BROWN if female else IRIS_BLUE, 0.3)
    pupil = material("HumanPupil", PUPIL, 0.3)
    skin = material("HumanSkinF" if female else "HumanSkinM", SKIN_F if female else SKIN, 0.55)
    objs = []
    r = 0.030
    for side in ("l", "r"):
        c = bone_head(arm, f"bone_kerbal_{side}_eye") + Vector((0, 0.012, 0))  # a little into the head
        ball = Builder(f"mesh_eye_human_{tag}_ball_{side}")
        ball.add(sphere(c, (r, r, r), 20, 14), None, white)
        ball.add(sphere(c + Vector((0, -r * 0.82, 0)), (r * 0.5, r * 0.28, r * 0.5), 16, 10), None, iris)
        ball.add(sphere(c + Vector((0, -r * 0.98, 0)), (r * 0.24, r * 0.16, r * 0.24), 12, 8), None, pupil)
        o = ball.build(col, arm, skinned=False)
        parent_to_bone(o, arm, f"bone_kerbal_{side}_eye")
        objs.append(o)
        # Upper lid covers the top ~30% of the eyeball, lower lid the bottom ~20% (open-eye look).
        for lid, plane_z, keep in (("u", c.z + 0.010, "front"), ("d", c.z - 0.017, "back")):
            lb = Builder(f"mesh_eyelid_human_{tag}_{side}{lid}")
            lid_bm = cut(sphere(c, (r + 0.004, r + 0.004, r + 0.004), 24, 16), (0, 0, plane_z), (0, 0, 1), keep)
            lb.add(lid_bm, None, skin)
            lo = lb.build(col, arm, skinned=False)
            parent_to_bone(lo, arm, f"bone_kerbal_{side}_eye_lid_{lid}")
            objs.append(lo)
    return objs


def build_helmet(arm, col):
    shell = Builder("mesh_helmet_human_01")
    white = material("HumanHelmet", SUIT_WHITE, 0.35)
    grey = material("HumanSuitGrey", SUIT_GREY, 0.5)
    center = Vector((0.0, -0.005, 0.485))
    rad = (0.178, 0.182, 0.178)
    # Bubble helmet: one tilted plane cut gives a round visor window; the shell keeps the rest.
    visor_plane = (center + Vector((0, -0.095, 0.01)), Vector((0, -1.0, 0.25)))
    back = cut(sphere(center, rad, 48, 32), visor_plane[0], visor_plane[1], keep="back")
    shell.add(back, None, white)
    shell.add(torus((0, -0.01, 0.352), 0.075, 0.014, 28, 10), None, grey)  # neck ring
    shell_obj = shell.build(col, arm, skinned=False)

    visor = Builder("mesh_helmet_human_01_visor")
    front = cut(sphere(center, (rad[0] - 0.003, rad[1] - 0.003, rad[2] - 0.003), 48, 32), visor_plane[0], visor_plane[1], keep="front")
    visor.add(front, None, material("HumanVisor", VISOR, 0.15))
    visor_obj = visor.build(col, arm, skinned=False)
    return [shell_obj, visor_obj]


def build_hair(arm, col, key, female, colour, style):
    b = Builder(f"hairstyle_{key}")
    mat = material(f"HumanHair_{key}", colour, 0.75)
    center = Vector((0.0, -0.002, 0.505))
    rad = (0.134, 0.138, 0.157) if not female else (0.130, 0.136, 0.156)
    cap = sphere_shaped(center, rad, head_shape(female), 40, 28)
    # Hairline: a tilted plane (normal up + slightly back) keeps the top/back of the skull; a second
    # cut trims the bottom edge so long styles stop at the neck/jaw.
    if style == "short":
        cut(cap, center + Vector((0, -0.02, 0.035)), (0, 0.35, 1.0), "front")
    elif style == "buzz":
        cut(cap, center + Vector((0, -0.02, 0.05)), (0, 0.3, 1.0), "front")
    elif style == "bob":
        cut(cap, center + Vector((0, -0.06, 0.02)), (0, 0.9, 0.55), "front")
        cut(cap, center + Vector((0, 0, -0.10)), (0, 0, 1.0), "front")
    else:  # long
        cut(cap, center + Vector((0, -0.06, 0.02)), (0, 0.9, 0.5), "front")
        cut(cap, center + Vector((0, 0, -0.16)), (0, 0, 1.0), "front")
    b.add(cap, None, mat)
    return b.build(col, arm, skinned=False)


# ---------------------------------------------------------------- rig helpers
def parent_to_bone(obj, arm, bone_name):
    world = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.matrix_world = world


def attached_export_matrix(arm, bone_name):
    """Local matrix (relative to an identity root empty) that makes Unity place the mesh in the local
    space of `bone_name` after the FBX round trip (mesh data is already in armature space). The root
    empty comes out rotated in Unity, but the game zeroes the attached prefab root's transform."""
    return arm.data.bones[bone_name].matrix_local.inverted()


# ---------------------------------------------------------------- export
FBX_COMMON = dict(
    apply_unit_scale=True,
    apply_scale_options="FBX_SCALE_ALL",
    axis_forward="-Z",
    axis_up="Y",
    use_mesh_modifiers=True,
    mesh_smooth_type="FACE",
    add_leaf_bones=False,
    primary_bone_axis="Y",
    secondary_bone_axis="X",
    armature_nodetype="NULL",
    bake_anim=False,
    path_mode="COPY",
    embed_textures=False,
    use_custom_props=False,
)


def select_only(objs):
    for o in bpy.data.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export_with_rig(arm, stem, meshes, out_dir):
    old = arm.name
    arm.name = stem
    select_only([arm] + meshes)
    path = os.path.join(out_dir, stem + ".fbx")
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, **FBX_COMMON)
    arm.name = old
    print("exported", path)


def export_attached(arm, stem, meshes, bone_name, out_dir):
    """Export meshes in the local space of `bone_name` (no armature), for attachToName prefabs."""
    export_matrix = attached_export_matrix(arm, bone_name)
    # A root empty named after the part guarantees Unity keeps a wrapper root (a single root mesh
    # would become the prefab root itself and lose its bone-local offset when the game zeroes it).
    root = bpy.data.objects.new(stem, None)
    bpy.context.collection.objects.link(root)
    root.matrix_world = Matrix.Identity(4)
    saved = []
    for m in meshes:
        saved.append((m, m.parent, m.parent_type, m.parent_bone, m.matrix_world.copy()))
        m.parent = root
        m.parent_type = "OBJECT"
        m.matrix_parent_inverse = Matrix.Identity(4)
        m.matrix_world = export_matrix
    select_only([root] + meshes)
    path = os.path.join(out_dir, stem + ".fbx")
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"EMPTY", "MESH"}, **FBX_COMMON)
    for m, parent, ptype, pbone, world in saved:
        m.parent = parent
        m.parent_type = ptype
        m.parent_bone = pbone
        m.matrix_world = world
    bpy.data.objects.remove(root)
    print("exported", path)


# ---------------------------------------------------------------- main
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else DEFAULT_ARGS
    out_dir, out_blend = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    os.makedirs(out_dir, exist_ok=True)
    arm = bpy.data.objects[ARM_NAME]

    # Move the stock reference meshes into a hidden collection so they never get exported.
    ref = bpy.data.collections.get("stock_reference") or bpy.data.collections.new("stock_reference")
    if ref.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(ref)
    for o in list(bpy.context.scene.collection.objects):
        if o.type == "MESH":
            bpy.context.scene.collection.objects.unlink(o)
            ref.objects.link(o)
    ref.hide_render = True
    ref.hide_viewport = True

    human = bpy.data.collections.get("human") or bpy.data.collections.new("human")
    if human.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(human)

    suit, backpack = build_suit(arm, human)
    jumpsuit = build_civilian_body(arm, human, "jumpsuit")
    scientist = build_civilian_body(arm, human, "scientist")
    head_m = build_head(arm, human, female=False)
    head_f = build_head(arm, human, female=True)
    eyes_m = build_eyes(arm, human, female=False)
    eyes_f = build_eyes(arm, human, female=True)
    helmet = build_helmet(arm, human)
    hair = {
        "human_m_01": build_hair(arm, human, "human_m_01", False, HAIR_BROWN, "short"),
        "human_m_02": build_hair(arm, human, "human_m_02", False, HAIR_BLACK, "buzz"),
        "human_f_01": build_hair(arm, human, "human_f_01", True, HAIR_BLOND, "long"),
        "human_f_02": build_hair(arm, human, "human_f_02", True, HAIR_RED, "bob"),
    }
    bpy.context.view_layer.update()

    export_with_rig(arm, "body_human_spacesuit_01", [suit, backpack], out_dir)
    export_with_rig(arm, "body_human_jumpsuit_01", [jumpsuit], out_dir)
    export_with_rig(arm, "body_human_scientist_01", [scientist], out_dir)
    export_with_rig(arm, "head_human_m_01", [head_m], out_dir)
    export_with_rig(arm, "head_human_f_01", [head_f], out_dir)
    export_with_rig(arm, "eyes_human_m_01", eyes_m, out_dir)
    export_with_rig(arm, "eyes_human_f_01", eyes_f, out_dir)
    export_attached(arm, "helm_human_spacesuit_01", helmet, "bone_kerbal_helmet", out_dir)
    for key, obj in hair.items():
        export_attached(arm, f"hair_{key}", [obj], "bone_kerbal_head", out_dir)

    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    print("saved", out_blend)


if __name__ == "__main__":
    main()
