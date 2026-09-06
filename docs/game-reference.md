# Game reference: how KSP2 Redux builds a kerbal

Everything below was read from the installed game (Redux 0.2.9.0 beta, build 26w35b) by decompiling
`Assembly-CSharp.dll` and parsing the Addressables catalog and bundles. It is the contract the human
assets must satisfy.

## 1. Install facts

| Item | Value |
| --- | --- |
| Install | `C:\Program Files (x86)\Steam\steamapps\common\Kerbal Space Program 2` |
| Redux version | 0.2.9.0.104355-beta (26w35b), channel `beta`, prepatched install |
| Engine | Unity 6000.5.8f1 (stock KSP2 bundles were built with 2022.3.5f1, Redux bundles with 6000.5.8f1) |
| Mod loader | SpaceWarp2 (built in), PatchManager, V-SwiFT, UITK for KSP2, ReduxLib |
| Mods folder | `<install>\mods\<ModName>\` containing `swinfo.json`; `main_assembly` names the DLL; `assets\addressables\catalog.json`, `assets\soundbanks\*.bnk`, `assets\localizations\*.csv`, `*.lua` scripts are auto-loaded |
| Audio | Wwise 2021.1.10, bank version 140 |
| Docs | https://docs.rendezvous.dev/s/0a4a3e31-0b40-48e0-bd81-e14856f80d3d |
| SDK | Redux SDK Manager v0.4.2 (`redux-sdk-gui.exe`), template repos `Redux.Template` (6000.4.1f1) and `Redux-Snapshot.Template` (6000.5.0f1) |

Addressables catalogs are consulted in registration order and `LoadAssetAsync(key)` returns the
first location found, so the stock catalog always wins for a duplicated key. Mods must use new keys.

## 2. The variety system (appearance generation)

`KerbalVarietySystem` (KSP.Game) loads every TextAsset labelled `kerbal_variety`:

| File pattern | Role | Merge rule when duplicated |
| --- | --- | --- |
| `KerbalAttributes_EVA.json`, `_PictureDay.json`, `_Colonist.json` | ordered attribute rules: `attributeName`, `dependsOn`, `attributeRangeRuleKey`, `preGenerationFunction`, `applyFunction` | per-attribute overwrite |
| `KerbalVarietyRangeRules.json` | range rules by name: MANIFEST (list), WEIGHTEDMANIFEST, SET, MINMAX, STATIC, with `subCategoryKey`, `probabilityOfEmpty`, `attachToName` | loading breaks if more than one asset has this key |
| `KerbalVarietyGameObjectCategories.json` | category -> list of prefab keys (BODY, HEAD, EYES, SPACESUIT, JUMPSUIT, HAIR, HELMET, HAT, FACEDECORATION, FACEDECORATION_SAFETY, KERBALIVA) | loading breaks if duplicated |
| `*_weighted_options.json` | weighted tables keyed by inner `Name` (EYES_OPTIONS_WEIGHTED, SKINCOLOR_OPTIONS_WEIGHTED, HAIRCOLOR_OPTIONS_WEIGHTED, FACIALHAIR_OPTIONS_WEIGHTED, FACEDETAIL_OPTIONS_WEIGHTED) | last loaded wins |
| `<lang>_<f|m|n>_names_kerbal.json` | name lists (ENGLISH_N_KERBALNAMES ...) | first loaded wins |
| `custom_kerbal` label: `Jebediah_Kerman.json` ... (85 files) | predefined kerbals with fixed attributes | n/a |

Attribute order for EVA (dependencies in brackets): NAME, SURNAME (GenerateSurname -> "Kerman"),
ORIGINTYPE, BODY [PlaceAndAnimateRig], TYPE (CIRCLE = `_F_` assets, SQUARE = `_M_` assets),
HEAD [ReSkinTheseMeshesToTheRootRig], EYES [ReParentAllMeshesToTheRootRig], HELMET (attach
`bone_kerbal_helmet`), HAIRSTYLE (attach `bone_kerbal_head`, TryConnectHairToHelmet), HAIRCOLOR,
EYEHEIGHT, SKINCOLOR [ApplyKerbalSkinColor], FACEDETAIL, FACEDECORATION (attach `bone_kerbal_head`),
FACIALHAIR [ReSkinAndConnectToHelmet], EYESYMMETRY, TEAMCOLOR1/2, STUPIDITY, BRAVERY, CONSTITUTION,
OPTIMISM, RADIATION, HAPPINESS, EXPERIENCE, BIOGRAPHY, ISVETERAN, VOICESELECTION, VOICETYPE.

Persistence: a save stores only `CustomNameKey`, `FirstName` and `Surname` per kerbal
(`SerializedKerbalAttributes`); every appearance attribute is regenerated on load from a randomizer
seeded with the full name and the attribute name (`GetSeededRandomizer`). Changing the option tables
therefore changes existing kerbals too, deterministically per name, and renaming a kerbal re-rolls
their look. MANIFEST picks go through the public `GetVarietySubCategoryByRangeRule`; WEIGHTEDMANIFEST
picks (`PregenerateWeightedManifest`) read the private `VarietyWeightedCategories` dictionary, which is
why the mod injects its tables there (`VarietyPatches.PregenerateWeightedManifest_Prefix`).

`Kerbal3DModel.PreloadAllAsyncAssets` loads each GameObject attribute with
`Assets.Load(value.ToLowerInvariant() + ".prefab")` and each texture attribute with
`... + ".png"`. So the table entry `HEAD_HUMAN_M_01` means an addressable prefab with key
`head_human_m_01.prefab` must exist in the mod catalog.

Predefined kerbal JSON (example `Jebediah_Kerman.json`):

```json
{ "JEBEDIAH_KERMAN": { "ORIGINTYPE": "HERO", "NAME": "Jebediah", "SURNAME": "Kerman", "TYPE": "SQUARE",
  "HAIRSTYLE": "HAIR_JEB", "HELMET": "HELM_SPACESUIT_01", "HAIRCOLOR": "55483F", "EYES": "EYES_M_01",
  "EYEHEIGHT": 0.0, "EYESYMMETRY": 1.0, "SKINCOLOR": "BADA55", "FACIALHAIR": "NONE",
  "FACEDECORATION": "NONE", "FACEDETAIL": "NONE", "TEAMCOLOR1": "BF0000", "TEAMCOLOR2": "BFBFBF",
  "STUPIDITY": 1.0, "BRAVERY": 1.0, "CONSTITUTION": 1.0, "OPTIMISM": 1.0, "ISVETERAN": true,
  "VOICESELECTION": 1, "VOICETYPE": 0.5 } }
```

## 3. Rig contract

The body prefab (`body_spacesuit_01.prefab` and friends) owns the skeleton. Heads, eyes, hair,
helmets and facial hair are separate prefabs that get merged onto it by name:

- `ReSkinTheseMeshesToTheRootRig` (HEAD, FACIALHAIR): every `SkinnedMeshRenderer` in the head prefab
  is re-bound to the body's bones by bone NAME (`SkinnedMeshUtils.ReplaceOldBonesWithNewBonesInSkinnedMesh`),
  then parented under the body object. Missing bone name = error and the mesh keeps its own bones.
- `ReParentAllMeshesToTheRootRig` (EYES): every `MeshRenderer` in the eyes prefab is re-parented under
  the body bone whose name equals the renderer's parent name (eye balls under `bone_kerbal_l_eye` /
  `bone_kerbal_r_eye`, lids under `bone_kerbal_*_eye_lid_u` / `_d`).
- HELMET, HAIR, FACEDECORATION are attached to `attachToName` bones (`bone_kerbal_helmet`,
  `bone_kerbal_head`) with identity local transform.
- The root object must have an `Animator`; `PlaceAndAnimateRig` zeroes the body transform and calls
  `Animator.Rebind()`. The first child whose name starts with `body_` is treated as the body, and the
  first child of it starting with `bone_` as the root bone.
- Helmet visibility toggles any object whose name contains `helmet`, starts with `helm_` or contains `_helm`.
- Jetpack root is found by tag `KerbalJetpackRoot`; EVA models root by tag `KerbalEVAModelsRoot`.

### Bone hierarchy (must be reproduced exactly, names and parenting)

```
body_<name>
  bone_kerbal_master_parent
    bone_kerbal_root
      bone_kerbal_pelvis
        bone_kerbal_l_thigh > bone_kerbal_l_knee > bone_kerbal_l_foot > bone_kerbal_l_toe
        bone_kerbal_r_thigh > bone_kerbal_r_knee > bone_kerbal_r_foot > bone_kerbal_r_toe
      bone_kerbal_spine_lower
        bone_kerbal_spine_upper
          bone_kerbal_eva_ach > bone_kerbal_eva_root            (jetpack: eva_l/r_arm01_pitcher > arm01_roll > arm02_pitcher > arm03_pitcher > arm03_roll > joystick_pitcher > joystick_rotator, plus mesh_backpack_01 / _door)
          bone_kerbal_l_collar > bone_kerbal_l_shoulder > bone_kerbal_l_elbow > bone_kerbal_l_hand
              bone_kerbal_l_hand_ach, l_middle_01/02/03, l_pinky_01/02/03, l_pointer_01/02/03, l_thumb_01/02/03
          bone_kerbal_r_collar > ... (mirror)
          bone_kerbal_neck_ach
            bone_kerbal_helmet
            bone_kerbal_neck > bone_kerbal_head
              bone_kerbal_jaw_d > jaw_d_lips_l, jaw_d_lips_lc, jaw_d_lips_r, jaw_d_lips_rc, jaw_d_teeth
              bone_kerbal_jaw_u > jaw_u_lips_l, jaw_u_lips_l_corner, jaw_u_lips_lc, jaw_u_lips_r, jaw_u_lips_r_corner, jaw_u_lips_rc, jaw_u_teeth
              bone_kerbal_l_eye_offset > bone_kerbal_l_eye, bone_kerbal_l_eye_lid_d, bone_kerbal_l_eye_lid_u
              bone_kerbal_r_eye_offset > bone_kerbal_r_eye, bone_kerbal_r_eye_lid_d, bone_kerbal_r_eye_lid_u
              bone_kerbal_tongue_01 > bone_kerbal_tongue_02
  mesh_<body>  (SkinnedMeshRenderer)
  <body>_reentry_meshes (SkinnedMeshRenderer + reentry component)
  mesh_<body>_hardware (SkinnedMeshRenderer)
```

Full transforms with local position/rotation/scale: `reference/hierarchies/body_spacesuit_01.json`.
Orientation facts: `bone_kerbal_master_parent` and every `mesh_*` object under the body are rotated
-90 degrees about X (the source model was authored Z-up), `bone_kerbal_root` sits 0.236 m up (its
local +Z), and skinned meshes are stored in that rotated mesh space. `tools/blender_build_rig.py`
rebuilds the armature and places the reference meshes with these transforms applied.
Bone names referenced directly by code: `bone_kerbal_master_parent`, `bone_kerbal_eva_ach`,
`bone_kerbal_eva_root`, `bone_kerbal_l_eye`, `bone_kerbal_r_eye`, `bone_kerbal_l_foot`,
`bone_kerbal_r_foot`, `helper_helmet_center_transform` (hair compression helper on the helmet).

### FBX round trip (Blender -> Unity), verified with `tools/compare_rig.py`

Blender's FBX exporter (default -Z forward / Y up) rotates only ROOT nodes by -90 degrees about X and
writes child transforms in Blender's own frame; Unity's importer then mirrors X on every node. To land
the stock bone transforms exactly:

- author in the scene frame C: Blender (x, y, z) = Unity (-x, -z, y), Z-up, character faces -Y;
- rotate the armature object +90 degrees about X (its exported root becomes identity);
- store each bone's armature-space matrix as the stock Unity world matrix conjugated by diag(-1, 1, 1);
- give mesh objects under the armature `matrix_world = A` with their data transformed by `A^-1`;
- for prefabs attached by `attachToName` (helmet, hair), export the mesh alone with
  `matrix_world = A @ bone.matrix_local.inverted()` so Unity gets the bone-local placement;
- Unity adds a file root above Blender's armature null; `HumanKerbalsBatch.ImportModels` flattens the
  null so bones and meshes sit directly under the `body_*` root like the stock prefabs.

`tools/blender_build_rig.py` and `tools/blender_make_human.py` implement this; `compare_rig.py`
must report MATCH before a body prefab is used.

### Animation

- Avatar `all_kerbal_partsAvatar` is GENERIC (no humanoid map); 166 clips in
  `kerbal_shared_assets_all.bundle`, controllers `animtree_kerbal_eva`, `animtree_kerbal_iva`,
  `animtree_kerbal_photobooth`. Root motion enabled.
- Facial animation is bone based (jaw, lips, eyelids, tongue), not blend shapes. Blinking is driven by
  `KerbalBlinking` (trigger `tBlink`, int `iBlinkChoice`) on the eyelid bones.
- Clips carry position + euler + scale curves for all 91 bones. Position is CONSTANT for most bones but
  ANIMATED for: knees (152 of 166 clips), jetpack arm/joystick bones, root, shoulders, neck, hand
  anchors, eyes and eyelids, elbows, hands, tongue, thumbs/fingers, jaw and lip bones, feet/toes,
  master_parent (36), neck_ach (36), eva_ach/eva_root (30). Consequence: a skeleton with different
  bone offsets gets partially snapped back to kerbal proportions by the animator. Options are in
  `docs/PLAN.md` Phase 3.
- Animation events used for sound: `PostAnimWWEvent(<event name>)`, plus `LeftFootprintEvent`,
  `RightFootprintEvent`, `Blink`, `DoJumpImpulse`, `AnimationEnd`. Keep these if clips are re-exported.

## 4. Materials and shaders

Character shader: `KSP2/Standard Character` (in `sharedshaders_assets_all.bundle`). Properties used
by code: `_RandomColor` (skin tint applied by `ApplyKerbalSkinColor` to every renderer using this
shader), `_FresnelScale`, `_MainTex`, plus `_BumpMap`, `_OcclusionMap`, `_MaskTex`, `_PaintMask`,
`_PaintColorA/B` (team colours), `_MetallicGlossMap`, `_EmissionMap`. Stock head material:
`kerbal_head_01_D` with `_MainTex` 1024 (albedo), `_BumpMap` 2048, `_OcclusionMap` 1024,
`_MaskTex` 1024 (skin mask deciding where the tint applies).

For human skin either keep the shader and let `_RandomColor` tint a neutral albedo through the mask
(gives the free skin-tone variety from `SKINCOLOR_OPTIONS_WEIGHTED`), or paint full-colour albedo and
set the mask black so the tint is ignored.

Hair shader `KerbalHair2.shader`; hair prefabs carry a `HairCompression` component that flattens hair
under the helmet using `helper_helmet_center_transform`.

Stock mesh budgets (for matching silhouette and LOD cost): head 2555 verts / 18 bones, eyes 2594,
spacesuit 7981 / 44 bones, suit hardware 6196, helmet 4548 + visor 321, jumpsuit 3530 / 47 bones,
backpack 3592.

## 5. Asset keys the mod must provide (Phase 1 minimum)

| Category | Stock keys | Human keys (from `human_variety.json`) |
| --- | --- | --- |
| BODY / SPACESUIT | body_spacesuit_01 | body_human_spacesuit_01 |
| BODY / JUMPSUIT | body_jumpsuit_01, body_jumpsuit_02 | body_human_jumpsuit_01 |
| HEAD | head_f_01, head_m_01 | head_human_f_01, head_human_m_01 |
| EYES | eyes_f_01, eyes_m_01 (+ raven, geareye, underlash) | eyes_human_f_01, eyes_human_m_01 |
| HELMET | helm_spacesuit_01 | helm_human_spacesuit_01 |
| HAIR | hair_f_01..10, hair_m_01..10, named styles | hair_human_f_01/02, hair_human_m_01/02 |
| KERBALIVA | kerbaliva | keep stock |

Type gating: TYPE CIRCLE picks entries containing `_F_`, SQUARE picks `_M_`, so keep the `_F_` /
`_M_` infix in human keys (`HEAD_HUMAN_F_01`). Keys are compared upper-case in tables and loaded
lower-case with `.prefab` appended.

## 6. Where things live (stock bundles)

| Content | Bundle |
| --- | --- |
| Animation clips, controllers, photobooth | `kerbal_shared_assets_all.bundle` |
| Skeleton + all base meshes + avatar | `49de7b4bc06c68e0430c39410ed0fc9a.bundle` |
| Head textures + material | `b461a5bfaceb826a5084c96d5f82024c.bundle`, mask in `569475380ec6cd5d2c71f799d2d8e25b.bundle` |
| Per-part prefabs | `kerbal_variety_assets_<part>.prefab.bundle` |
| Variety JSON | `kerbal_variety_text_assets_all.bundle` |
| EVA part prefab (`eva_kerbal.prefab`) | `5d2a68a862c72f92df5e1f207ef87e91.bundle` |
| Redux additions (helmet lights, suit emissive) | `Redux\Addressables\StandaloneWindows64\kerbal_assets_all_*.bundle` |

## 7. Text

The word "Kerbal" appears in about 90 lines of the Redux OTA CSVs (`%LOCALAPPDATA%Low\Intercept
Games\Kerbal Space Program 2\Ksp2Redux\OtaContent\localizations`) and in many more stock terms
inside `localizations_assets_all.bundle`. Mod CSVs are inserted at index 0 of the I2 sources, so a
mod term overrides the stock one with the same key.

## 8. Menu-room actors (Mission Control, main menu)

The kerbals seen in Mission Control (console rows, the scientists on the big screens, Keri Kerman,
the hall walker) and in the main-menu vignettes are not roster kerbals. The Mission Control scene
(`menuback_missioncontrol`, bundle `missioncontrol_scenes_all.bundle`) holds ten `RandomPrefabLoader`
components; each one instantiates a finished `RPLT_*` actor prefab from
`missioncontrol_assets_all.bundle` (main-menu plates: `ui_assets_all.bundle`) and calls
`RandomPrefabLoader_Target.Init` on it. An actor prefab is:

| Object | Content |
| --- | --- |
| actor root | `ShowRandomMeshByKerbalType` (picks CIRCLE = female or SQUARE = male, hides the other head), `AnimatorEventsToggle`, `ActorMaterialColors` (skin/hair tint through `_RandomColor` on the KSP2 character shaders, random face-detail albedo on renderers whose name contains `_head_`) |
| `rig` | `Animator` with its own controller (`animtree_kerbal_npc_scientist`, `animtree_bg_misscon_sitting`, `animtree_kerbal_mc_keri_kerman`), `ShowRandomSetOfGameObjects`, `SimpleFidgetManager`, `KerbalBlinking`; children: the full `bone_kerbal_*` skeleton plus the body/head/beard skinned meshes |
| `rig/mesh_body_scientist_01` | body `SkinnedMeshRenderer`, 43 bones, root `bone_kerbal_spine_lower` (main-menu EVA actors use `mesh_spacesuit_01` + `_hardware`) |
| `rig/mesh_male_head_01`, `rig/mesh_female_head_01` | both stock heads, 18 bones, root `bone_kerbal_neck` |
| `rig/facialhair/*` | every stock beard mesh, skinned to the head bones |
| `.../bone_kerbal_head/actor_hairstyles/random/hair_(m|f)_*/hairstyle_*` | every stock hairstyle as `MeshRenderer` + `HairCompression` |
| `.../bone_kerbal_head/actor_glasses/random/deco_face_glasses_*` | stock glasses |
| `.../bone_kerbal_(l|r)_eye*/mesh_eye_*`, `mesh_eyelid_*` | stock eyeballs and lids as `MeshRenderer`s, all variants present |

Nothing here touches `KerbalVarietySystem` or `Kerbal3DModel`, so the variety patches never run for
them. The mod converts them at spawn time instead (`Code/ActorPatches.cs`, data in the `actorSwap`
block of `human_variety.json`): a Harmony postfix on `RandomPrefabLoader_Target.Init` finds every
`bone_kerbal_master_parent` in the spawned prefab and applies the same operations the game uses for
roster kerbals: `SkinnedMeshUtils.ReplaceOldBonesWithNewBonesInSkinnedMesh` semantics for the human
body and head (bones matched by name, then parented under `rig`), `ReParentAllMeshesToTheRootRig`
semantics for the eyes (`SetParent(bone, worldPositionStays: false)` under the bone named like the
prefab parent), `AttachToNamedParent` semantics for hair and helmet (identity local transform under
`bone_kerbal_head` / `bone_kerbal_helmet`), then `Animator.Rebind()`. The stock body, heads, eyes,
hairstyle container (and, by default, beards) are deactivated; `ActorMaterialColors` is stopped
because its face-detail step would put a kerbal face texture on the human head material. The body
kind comes from the stock mesh name (`scientist`, `jumpsuit`, `groundcrew`, `worker`, `spacesuit`)
and maps to a preference list of human bodies, so a missing part falls back to the next one.

These pre-rendered paths do not pass through actor conversion: Keri Kerman in the Training Center
and mission dialogs uses video/GIF loops in `gifs_assets_all.bundle`. The first-run orientation clip
(`tutorial_01_SpaceisthePlace_v13`) is explicitly redirected to the human-only Gerbal film, and the
known `Gif_Test_TalkingKerbal` helper loop has its own sprite-sheet redirect. Other dedicated
Training Center and mission-dialog clips remain stock. The 2D tech-tree backgrounds of the R&D center
also remain stock (`research_assets_all.bundle` holds only UI and sprites, no kerbals).
`SpaceCenterCrew`, `Scientist` and `GroundCrew` in the assembly are KSP1 leftovers that no bundle
references.
