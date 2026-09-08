# Tools

Python helpers for reading the KSP2 Redux install. Create the venv once:

```powershell
python -m venv tools\venv
tools\venv\Scripts\python -m pip install -r tools\requirements.txt
```

All scripts locate the game through `ksp2paths.py` (Steam default path, or set `KSP2_PATH`).

| Script | Purpose |
| --- | --- |
| `extract_reference.py` | Export kerbal meshes (OBJ), textures (PNG), material property dumps, prefab hierarchies (JSON) and the animation clip/event list into `reference/` |
| `catalog_keys.py <catalog.json> <regex>` | List addressable keys matching a regex |
| `catalog_resolve.py <catalog.json> <regex>` | Resolve keys to provider, type and the bundle files that supply them |
| `bundle_list.py <bundle> [regex] [text]` | List objects in a bundle; with `text` also print matching TextAsset contents |
| `bundle_hierarchy.py <bundle> [depth]` | Print the GameObject/Transform tree of a prefab bundle |
| `bundle_materials.py <bundle...>` | Print shader names and material properties |
| `anim_events.py <bundle>` | Aggregate animation events (sound hooks) across clips |
| `anim_streamed_bones.py <clipBundle> <avatarBundle>` | Which bones have animated position curves (rig proportion constraint) |
| `bnk_parse.py <file.bnk>` | Parse a Wwise bank: sections, embedded media, HIRC object counts, event IDs |
| `bnk_media_xref.py <audioDir>` | Which event banks reference the kerbal voice/SFX media banks |
| `wwise_fnv.py <id,id,...> <name...>` | Hash candidate event names (FNV-1 32) and mark matches |
| `wwise_scan_refs.py <aaDir> <out.json> <maxBytes>` | Scan bundles for Wwise object references (event name to ID) |
| `wwise_bank_write.py <spec.json> <out.bnk>` | Write a Wwise 2021.1 (format 140) soundbank with embedded PCM clips, one Sound + Play action + Event per clip, no authoring tool needed |
| `vo_transcribe.py [workdir]` | Decode the English narration `.wem` files (vgmstream) and transcribe them with word timestamps (faster-whisper, CPU) |
| `vo_gerbal.py <events|transcribe|edit|bank|all> [--verify]` | Narration pipeline: find every spoken "Kerbal", re-cut the /k/ into a /g/, generate `HumbleSpaceProgram_narration.bnk` and `narration_remap.json` |
| `vgmstream/vgmstream-cli.exe` | Decodes `.wem` and `.bnk` media to WAV (`-m` prints metadata) |
| `wwiser/wwiser.pyz` | Wwise bank parser (`-d xml` dump, `-g` per-event `.txtp` play lists) |

`UnityPy` reads Unity 2022 and Unity 6 bundles. It cannot export animation clips; use AssetRipper
for FBX/anim export when retargeting (plan Phase 3b).

## Build and test scripts

| Script | Purpose |
| --- | --- |
| `sdk\redux-sdk-cli.exe` | Redux SDK Manager CLI (v0.4.2): `versions`, `create`, `setup --ksp2 <exe> <project>`, `projects` |
| `unity_batch.ps1 -Method HumbleSpaceProgramBatch.<SetupMod|BuildForPlayer|Deploy>` | Runs the Unity 6000.5.8f1 editor headless on `unity\`; logs land in `logs\unity_<method>.log` |
| `verify_in_game.ps1` | Starts KSP2, waits for `Registered plugin: HumbleSpaceProgram` and the plugin's init lines, prints matching log lines, closes the game |
| `blender_build_rig.py` | Rebuilds the kerbal armature and places the stock reference meshes in `blender\kerbal_rig.blend` (frame conventions documented in the file) |
| `blender_make_human.py` | Generates the stylised human parts on the rig (spacesuit, jumpsuit and lab-coat bodies, heads, eyes, helmet, hair), saves `blender\human_rig.blend`, exports the twelve part FBX files into `unity\Assets\HumbleSpaceProgram\Models` |
| `blender_export_parts.py` | Generic exporter for hand-modelled parts (same naming contract) |
| `compare_rig.py [model]` | Compares bones of an imported model (from `HumbleSpaceProgramBatch.ImportModels`) against the stock rig; must print MATCH |
| `unity_batch.ps1 -Method HumbleSpaceProgramBatch.ImportModels` | Imports the FBX files, creates prefabs, registers addressable keys, dumps hierarchies |
| `unity_batch.ps1 -Method HumbleSpaceProgramBatch.ValidateHumanSize` | Bakes resized body/head meshes and verifies adult height; writes `logs/human-size-validation.txt` |
| `verify_in_game.ps1 -TestLoad` | Launches the game in test mode: auto-loads the newest save, dumps every kerbal portrait PNG to `logs\portraits`, quits |
| `verify_in_game.ps1 -MissionControl` | As `-TestLoad`, then enters Mission Control and saves three screenshots of the converted actor prefabs to `logs\missioncontrol` |
| `verify_in_game.ps1 -AudioTest` | Launches the game, posts the remapped narration events from the main menu and prints the Wwise playing ids, durations and monitor errors (`AUDIO:` lines) |

`BuildForPlayer` stages the mod into `<KSP2>\mods\__Testing\HumbleSpaceProgram`; `Deploy` writes
`unity\Deploy\HumbleSpaceProgram.zip` for distribution.

Normal startup resumes the newest autosave and enters Mission Control. Launch with
`-humblespaceprogram-startup-capture "<directory>"` to capture three screenshots after that normal
startup completes, without enabling test mode or quitting the game. `-humblespaceprogram-menu`
disables automatic resume for that launch.
