// Headless helpers for the Humble Space Program mod project.
//
// Run through tools/unity_batch.ps1, which starts the editor WITHOUT -quit so the editor loop keeps
// pumping async ThunderKit pipelines; every entry point ends by calling EditorApplication.Exit.
//
//   powershell -File tools\unity_batch.ps1 -Method HumbleSpaceProgramBatch.SetupMod
//   powershell -File tools\unity_batch.ps1 -Method HumbleSpaceProgramBatch.BuildForPlayer
//   powershell -File tools\unity_batch.ps1 -Method HumbleSpaceProgramBatch.Deploy
//
// SetupMod mirrors what "Modding > Create New Mod" does in the SDK (CreateNewModWindow.CreateMod) and
// then swaps the generated template plugin for the files staged in <project>/Staging/Code.

using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Ksp2UnityTools.Editor;
using Ksp2UnityTools.Editor.Modding;
using UnityEditor;
using UnityEngine;
using UnityEngine.Video;

public static class HumbleSpaceProgramBatch
{
    private const string ModId = "HumbleSpaceProgram";
    private const string ModFolder = "Assets/" + ModId;
    private const string ModAssetPath = ModFolder + "/" + ModId + ".asset";
    private const string StagedCode = "Staging/Code";

    public static void SetupMod()
    {
        try
        {
            SetupModInternal();
            Debug.Log("[HumbleSpaceProgramBatch] SetupMod done.");
            Exit(0);
        }
        catch (Exception e)
        {
            Debug.LogError("[HumbleSpaceProgramBatch] SetupMod failed: " + e);
            Exit(1);
        }
    }

    private static void SetupModInternal()
    {
        Directory.CreateDirectory(ModFolder);
        Directory.CreateDirectory(ModFolder + "/Copied");
        Directory.CreateDirectory(ModFolder + "/Copied/localizations");
        Directory.CreateDirectory(ModFolder + "/Copied/Patches");
        Directory.CreateDirectory(ModFolder + "/Definitions/Parts");
        Directory.CreateDirectory(ModFolder + "/Definitions/Missions");
        Directory.CreateDirectory(ModFolder + "/Definitions/Experiments");
        AssetDatabase.Refresh();

        var mod = AssetDatabase.LoadAssetAtPath<Mod>(ModAssetPath);
        if (mod == null)
        {
            mod = ScriptableObject.CreateInstance<Mod>();
            mod.id = ModId;
            AssetDatabase.CreateAsset(mod, ModAssetPath);
        }

        mod.name = "Humble Space Program";
        mod.author = "tano";
        mod.description = "Makes the program human: Gerbal models, textures, names, narration, and sound effects.";
        mod.version = "0.1.0";
        mod.source = "https://github.com/tanodeluca/HumbleSpaceProgram";
        mod.minKsp2Version = "0.2.9";
        mod.maxKsp2Version = "*";
        mod.dependencies.Clear();
        mod.dependencies.Add(new ModDependency { id = "SpaceWarp2", min = "2.0.0", max = "*" });
        mod.dependencies.Add(new ModDependency { id = "Ksp2Redux", min = "0.2.9", max = "*" });
        mod.dependencies.Add(new ModDependency { id = "PatchManager", min = "0.0.0", max = "*" });
        mod.SyncPickerDisplayName();
        EditorUtility.SetDirty(mod);
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        if (!File.Exists(mod.AssemblyPath))
        {
            mod.CreateAssembly();
        }

        // Replace the SDK's template plugin with the staged sources.
        if (Directory.Exists(StagedCode))
        {
            var template = mod.MainPluginPath;
            if (File.Exists(template) && !File.Exists(Path.Combine(StagedCode, Path.GetFileName(template))))
            {
                AssetDatabase.DeleteAsset(template);
            }
            foreach (var file in Directory.GetFiles(StagedCode, "*.cs"))
            {
                File.Copy(file, Path.Combine(ModFolder, "Code", Path.GetFileName(file)), true);
            }
        }

        mod.CreateAddressablesGroups();
        ImportVisualAssetsInternal();
        mod.RefreshPipelines();
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
    }

    // Same as the SDK's "Test Selected Mods in Built Game" minus launching KSP2 afterwards: stages the
    // mod into <GamePath>/mods/__Testing/<id>. Use tools/verify_in_game.ps1 to run the game.
    public static void BuildForPlayer()
    {
        RunPipeline("BuildForPlayer", mod =>
        {
            var settings = ThunderKit.Core.Data.ThunderKitSetting.GetOrCreateSettings<ThunderKit.Core.Data.ThunderKitSettings>();
            var testingFolder = Path.Combine(settings.GamePath, "mods/__Testing");
            if (Directory.Exists(testingFolder))
            {
                Directory.Delete(testingFolder, true);
            }
            var pipeline = AssetDatabase.LoadAssetAtPath<ThunderKit.Core.Pipelines.Pipeline>(mod.Folder + "/Pipelines/Build for Player.asset");
            if (pipeline == null)
            {
                throw new FileNotFoundException("Build for Player pipeline missing; run SetupMod first.");
            }
            return pipeline.Execute();
        });
    }

    public static void Deploy()
    {
        RunPipeline("Deploy", mod => KSP2UnityToolsManager.DeployMods(mod));
    }

    // ---- Models -> prefabs -> addressables ------------------------------------------------------

    private const string ModelsFolder = ModFolder + "/Models";
    private const string PrefabsFolder = ModFolder + "/Prefabs";
    private const string TexturesFolder = ModFolder + "/Textures";
    private const string VideosFolder = ModFolder + "/Videos";
    private const string LoadingTexturePath = TexturesFolder + "/human_loading_screen.png";
    private const string LoadingTextureAddress = "human_loading_screen_texture";
    private const string TalkingGerbalTexturePath = TexturesFolder + "/human_gerbal_intro_sheet.png";
    private const string TalkingGerbalTextureAddress = "human_gerbal_intro_sheet";
    private const string OrientationVideoPath = VideosFolder + "/human_gerbal_orientation.mp4";
    private const string OrientationVideoAddress = "human_gerbal_orientation_video";

    /// Imports and registers the human visual replacements: Texture2D for Redux's UI Toolkit loading
    /// flow, a transparent six-frame sprite sheet for talking helper loops, and a VideoClip for the
    /// first-run orientation film.  Runtime patches redirect stock players, leaving game bundles intact.
    public static void ImportVisualAssets()
    {
        try
        {
            ImportVisualAssetsInternal();
            Debug.Log("[HumbleSpaceProgramBatch] ImportVisualAssets done.");
            Exit(0);
        }
        catch (Exception e)
        {
            Debug.LogError("[HumbleSpaceProgramBatch] ImportVisualAssets failed: " + e);
            Exit(1);
        }
    }

    private static void ImportVisualAssetsInternal()
    {
        var mod = AssetDatabase.LoadAssetAtPath<Mod>(ModAssetPath);
        if (mod == null) throw new FileNotFoundException("Mod asset missing; run SetupMod first.");
        if (!File.Exists(LoadingTexturePath))
        {
            throw new FileNotFoundException("Missing generated human loading artwork: " + LoadingTexturePath);
        }
        if (!File.Exists(TalkingGerbalTexturePath))
        {
            throw new FileNotFoundException("Missing generated human Gerbal talking-loop sheet: " + TalkingGerbalTexturePath);
        }
        if (!File.Exists(OrientationVideoPath))
        {
            throw new FileNotFoundException("Missing generated human Gerbal orientation video: " + OrientationVideoPath);
        }

        Directory.CreateDirectory(TexturesFolder);
        Directory.CreateDirectory(VideosFolder);
        AssetDatabase.Refresh();
        var textureImporter = AssetImporter.GetAtPath(LoadingTexturePath) as TextureImporter;
        if (textureImporter == null) throw new Exception("No TextureImporter for " + LoadingTexturePath);
        var changed = false;
        if (textureImporter.textureType != TextureImporterType.Default) { textureImporter.textureType = TextureImporterType.Default; changed = true; }
        if (!textureImporter.sRGBTexture) { textureImporter.sRGBTexture = true; changed = true; }
        if (textureImporter.mipmapEnabled) { textureImporter.mipmapEnabled = false; changed = true; }
        // Preserve the generated 16:9 composition.  Unity otherwise rounds non-power-of-two artwork
        // to 2048x1024, which subtly stretches it on Redux's 16:9 loading panel.
        if (textureImporter.npotScale != TextureImporterNPOTScale.None) { textureImporter.npotScale = TextureImporterNPOTScale.None; changed = true; }
        if (textureImporter.maxTextureSize < 2048) { textureImporter.maxTextureSize = 2048; changed = true; }
        if (changed) textureImporter.SaveAndReimport();

        var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(LoadingTexturePath);
        if (texture == null) throw new Exception("Could not import " + LoadingTexturePath);

        var talkingImporter = AssetImporter.GetAtPath(TalkingGerbalTexturePath) as TextureImporter;
        if (talkingImporter == null) throw new Exception("No TextureImporter for " + TalkingGerbalTexturePath);
        var talkingChanged = false;
        if (talkingImporter.textureType != TextureImporterType.Default) { talkingImporter.textureType = TextureImporterType.Default; talkingChanged = true; }
        if (!talkingImporter.sRGBTexture) { talkingImporter.sRGBTexture = true; talkingChanged = true; }
        if (talkingImporter.mipmapEnabled) { talkingImporter.mipmapEnabled = false; talkingChanged = true; }
        if (talkingImporter.npotScale != TextureImporterNPOTScale.None) { talkingImporter.npotScale = TextureImporterNPOTScale.None; talkingChanged = true; }
        if (!talkingImporter.alphaIsTransparency) { talkingImporter.alphaIsTransparency = true; talkingChanged = true; }
        if (talkingImporter.filterMode != FilterMode.Point) { talkingImporter.filterMode = FilterMode.Point; talkingChanged = true; }
        if (talkingImporter.wrapMode != TextureWrapMode.Clamp) { talkingImporter.wrapMode = TextureWrapMode.Clamp; talkingChanged = true; }
        if (talkingChanged) talkingImporter.SaveAndReimport();

        var talkingSheet = AssetDatabase.LoadAssetAtPath<Texture2D>(TalkingGerbalTexturePath);
        if (talkingSheet == null) throw new Exception("Could not import " + TalkingGerbalTexturePath);
        if (talkingSheet.width != 256 || talkingSheet.height != 384)
        {
            throw new Exception($"Human Gerbal talking-loop sheet must be 256x384, got {talkingSheet.width}x{talkingSheet.height}");
        }

        var orientationVideo = AssetDatabase.LoadAssetAtPath<VideoClip>(OrientationVideoPath);
        if (orientationVideo == null) throw new Exception("Could not import " + OrientationVideoPath);

        var settings = UnityEditor.AddressableAssets.AddressableAssetSettingsDefaultObject.Settings;
        var group = mod.allGroup != null ? mod.allGroup : settings.FindGroup(g => g != null && g.name == "addressables_" + ModId + "_all");
        if (group == null) throw new Exception("Addressable group addressables_" + ModId + "_all missing; run SetupMod first.");
        RegisterAddressable(settings, group, LoadingTexturePath, LoadingTextureAddress);
        RegisterAddressable(settings, group, TalkingGerbalTexturePath, TalkingGerbalTextureAddress);
        RegisterAddressable(settings, group, OrientationVideoPath, OrientationVideoAddress);
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Debug.Log($"[HumbleSpaceProgramBatch] loading artwork: {texture.width}x{texture.height}, address {LoadingTextureAddress}");
        Debug.Log($"[HumbleSpaceProgramBatch] talking Gerbal sheet: {talkingSheet.width}x{talkingSheet.height}, address {TalkingGerbalTextureAddress}");
        Debug.Log($"[HumbleSpaceProgramBatch] orientation video: {orientationVideo.name}, address {OrientationVideoAddress}");
    }

    private static void RegisterAddressable(UnityEditor.AddressableAssets.Settings.AddressableAssetSettings settings,
                                            UnityEditor.AddressableAssets.Settings.AddressableAssetGroup group,
                                            string assetPath, string address)
    {
        var guid = AssetDatabase.AssetPathToGUID(assetPath);
        if (string.IsNullOrEmpty(guid)) throw new Exception("No GUID for " + assetPath);
        var entry = settings.CreateOrMoveEntry(guid, group, false, false);
        entry.address = address;
    }

    /// Imports every FBX in Assets/HumbleSpaceProgram/Models as a plain (non-animated) model, wraps it in a
    /// prefab named after the file, registers the prefab as an addressable with address "<name>.prefab"
    /// in the mod's main group, and dumps the bone hierarchy of body_* models for verification.
    public static void ImportModels()
    {
        try
        {
            ImportModelsInternal();
            Debug.Log("[HumbleSpaceProgramBatch] ImportModels done.");
            Exit(0);
        }
        catch (Exception e)
        {
            Debug.LogError("[HumbleSpaceProgramBatch] ImportModels failed: " + e);
            Exit(1);
        }
    }

    private static void ImportModelsInternal()
    {
        var mod = AssetDatabase.LoadAssetAtPath<Mod>(ModAssetPath);
        if (mod == null) throw new FileNotFoundException("Mod asset missing; run SetupMod first.");
        ImportVisualAssetsInternal();
        Directory.CreateDirectory(PrefabsFolder);
        AssetDatabase.Refresh();

        var settings = UnityEditor.AddressableAssets.AddressableAssetSettingsDefaultObject.Settings;
        var group = mod.allGroup != null ? mod.allGroup : settings.FindGroup(g => g != null && g.name == "addressables_" + ModId + "_all");
        if (group == null) throw new Exception("Addressable group addressables_" + ModId + "_all missing; run SetupMod first.");

        var dump = new System.Text.StringBuilder();
        foreach (var fbx in Directory.GetFiles(ModelsFolder, "*.fbx").OrderBy(p => p))
        {
            var assetPath = fbx.Replace('\\', '/');
            var stem = Path.GetFileNameWithoutExtension(assetPath);
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) { Debug.LogWarning("No ModelImporter for " + assetPath); continue; }
            var changed = false;
            // Rig "None" drops skinning entirely; Generic keeps SkinnedMeshRenderers. NoAvatar avoids an
            // Animator/Avatar on our prefab (the game's Animator lives on the parent object).
            if (importer.animationType != ModelImporterAnimationType.Generic) { importer.animationType = ModelImporterAnimationType.Generic; changed = true; }
            if (importer.avatarSetup != ModelImporterAvatarSetup.NoAvatar) { importer.avatarSetup = ModelImporterAvatarSetup.NoAvatar; changed = true; }
            if (importer.importAnimation) { importer.importAnimation = false; changed = true; }
            if (importer.importBlendShapes) { importer.importBlendShapes = false; changed = true; }
            if (importer.materialImportMode != ModelImporterMaterialImportMode.ImportStandard) { importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard; changed = true; }
            if (importer.materialLocation != ModelImporterMaterialLocation.InPrefab) { importer.materialLocation = ModelImporterMaterialLocation.InPrefab; changed = true; }
            if (!importer.isReadable) { importer.isReadable = true; changed = true; }
            if (changed) importer.SaveAndReimport();

            var model = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            if (model == null) { Debug.LogWarning("Model failed to import: " + assetPath); continue; }

            var instance = (GameObject)PrefabUtility.InstantiatePrefab(model);
            instance.name = stem;
            PrefabUtility.UnpackPrefabInstance(instance, PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
            FlattenArmatureNull(instance);
            foreach (var animator in instance.GetComponentsInChildren<Animator>(true))
            {
                UnityEngine.Object.DestroyImmediate(animator);
            }
            foreach (var smr in instance.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                TrimUnusedBones(smr, stem);
            }
            if (stem.StartsWith("body_"))
            {
                // Stock body prefabs: root tagged KerbalEVAModelsRoot (Kerbal3DModel needs it, null
                // reference otherwise) and the jetpack bone tagged KerbalJetpackRoot (hidden in IVA).
                TrySetTag(instance, "KerbalEVAModelsRoot");
                var jetpack = FindDeep(instance.transform, "bone_kerbal_eva_root");
                if (jetpack != null) TrySetTag(jetpack.gameObject, "KerbalJetpackRoot");
            }
            var prefabPath = PrefabsFolder + "/" + stem + ".prefab";
            var prefab = PrefabUtility.SaveAsPrefabAsset(instance, prefabPath);
            UnityEngine.Object.DestroyImmediate(instance);

            var guid = AssetDatabase.AssetPathToGUID(prefabPath);
            var entry = settings.CreateOrMoveEntry(guid, group, false, false);
            entry.address = stem.ToLowerInvariant() + ".prefab";
            Debug.Log($"[HumbleSpaceProgramBatch] {stem}: prefab {prefabPath}, address {entry.address}");

            DumpHierarchy(prefab.transform, "", dump, stem);
        }
        settings.SetDirty(UnityEditor.AddressableAssets.Settings.AddressableAssetSettings.ModificationEvent.EntryModified, null, true, true);
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Directory.CreateDirectory("../logs");
        File.WriteAllText("../logs/unity_prefab_hierarchies.jsonl", dump.ToString());
    }

    /// Blender exports a skin cluster for every armature bone, so Unity lists all 91 bones on each
    /// SkinnedMeshRenderer. The game re-skins parts by bone name and gives up on the whole mesh when any
    /// listed bone is missing (the photo booth removes the jetpack bones, for instance), so keep only the
    /// bones that carry weight. The trimmed mesh is saved as its own asset next to the prefab.
    private static void TrimUnusedBones(SkinnedMeshRenderer smr, string stem)
    {
        var mesh = smr.sharedMesh;
        if (mesh == null || smr.bones == null || smr.bones.Length == 0) return;
        var weights = mesh.boneWeights;
        var used = new bool[smr.bones.Length];
        foreach (var w in weights)
        {
            if (w.weight0 > 0f) used[w.boneIndex0] = true;
            if (w.weight1 > 0f) used[w.boneIndex1] = true;
            if (w.weight2 > 0f) used[w.boneIndex2] = true;
            if (w.weight3 > 0f) used[w.boneIndex3] = true;
        }
        var remap = new int[smr.bones.Length];
        var newBones = new System.Collections.Generic.List<Transform>();
        var newBind = new System.Collections.Generic.List<Matrix4x4>();
        var oldBind = mesh.bindposes;
        for (var i = 0; i < smr.bones.Length; i++)
        {
            if (!used[i]) { remap[i] = 0; continue; }
            remap[i] = newBones.Count;
            newBones.Add(smr.bones[i]);
            newBind.Add(oldBind[i]);
        }
        if (newBones.Count == smr.bones.Length) return;

        var copy = UnityEngine.Object.Instantiate(mesh);
        copy.name = mesh.name;
        for (var i = 0; i < weights.Length; i++)
        {
            var w = weights[i];
            w.boneIndex0 = w.weight0 > 0f ? remap[w.boneIndex0] : 0;
            w.boneIndex1 = w.weight1 > 0f ? remap[w.boneIndex1] : 0;
            w.boneIndex2 = w.weight2 > 0f ? remap[w.boneIndex2] : 0;
            w.boneIndex3 = w.weight3 > 0f ? remap[w.boneIndex3] : 0;
            weights[i] = w;
        }
        copy.boneWeights = weights;
        copy.bindposes = newBind.ToArray();
        var meshPath = PrefabsFolder + "/" + stem + "_" + mesh.name + ".asset";
        AssetDatabase.CreateAsset(copy, meshPath);
        smr.sharedMesh = AssetDatabase.LoadAssetAtPath<Mesh>(meshPath);
        smr.bones = newBones.ToArray();
        Debug.Log($"[HumbleSpaceProgramBatch] {stem}/{mesh.name}: trimmed bones {smr.bones.Length} -> {newBones.Count} ({string.Join(",", newBones.Select(b => b.name))})");
    }

    private static void TrySetTag(GameObject go, string tag)
    {
        try
        {
            go.tag = tag;
            Debug.Log($"[HumbleSpaceProgramBatch] tagged {go.name} as {tag}");
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[HumbleSpaceProgramBatch] could not tag {go.name} as {tag} (add it to the TagManager): {e.Message}");
        }
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

    /// Unity wraps the FBX in a root named after the file; Blender adds an armature null below it. The
    /// stock body prefabs have bones and meshes directly under the root, and the game looks for the
    /// first child starting with "bone_" on the body root, so move the null's children up one level.
    private static void FlattenArmatureNull(GameObject root)
    {
        for (var i = root.transform.childCount - 1; i >= 0; i--)
        {
            var child = root.transform.GetChild(i);
            var isNull = child.GetComponents<Component>().Length == 1 && child.childCount > 0 &&
                         child.name == root.name;
            if (!isNull) continue;
            var grandChildren = new System.Collections.Generic.List<Transform>();
            for (var j = 0; j < child.childCount; j++) grandChildren.Add(child.GetChild(j));
            foreach (var g in grandChildren) g.SetParent(root.transform, true);
            foreach (var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                if (smr.rootBone == child) smr.rootBone = root.transform.Find("bone_kerbal_master_parent");
            }
            UnityEngine.Object.DestroyImmediate(child.gameObject);
        }
    }

    private static void DumpHierarchy(Transform t, string parent, System.Text.StringBuilder sb, string stem)
    {
        var p = t.localPosition; var r = t.localRotation; var s = t.localScale;
        var comps = string.Join("|", t.GetComponents<Component>().Where(c => c != null && !(c is Transform)).Select(c => c.GetType().Name));
        var smr = t.GetComponent<SkinnedMeshRenderer>();
        if (smr != null)
        {
            var b = smr.localBounds;
            comps += $"|SMR(bones={smr.bones.Length},root={(smr.rootBone ? smr.rootBone.name : "null")},mesh={(smr.sharedMesh ? smr.sharedMesh.name : "null")},verts={(smr.sharedMesh ? smr.sharedMesh.vertexCount : 0)},bindposes={(smr.sharedMesh ? smr.sharedMesh.bindposes.Length : 0)},boundsCenter=({b.center.x:F3};{b.center.y:F3};{b.center.z:F3}),boundsExt=({b.extents.x:F3};{b.extents.y:F3};{b.extents.z:F3}),boneNames={string.Join(";", smr.bones.Select(x => x ? x.name : "null"))})";
        }
        var mr = t.GetComponent<MeshRenderer>();
        if (mr != null)
        {
            var b = mr.bounds;
            comps += $"|MR(mats={string.Join(";", mr.sharedMaterials.Select(m => m ? m.name + ":" + m.shader.name : "null"))},boundsCenter=({b.center.x:F3};{b.center.y:F3};{b.center.z:F3}),boundsExt=({b.extents.x:F3};{b.extents.y:F3};{b.extents.z:F3}))";
        }
        sb.Append("{\"model\":\"").Append(stem).Append("\",\"name\":\"").Append(t.name).Append("\",\"parent\":\"").Append(parent)
          .Append("\",\"pos\":[").Append(p.x.ToString("R")).Append(',').Append(p.y.ToString("R")).Append(',').Append(p.z.ToString("R"))
          .Append("],\"rot\":[").Append(r.x.ToString("R")).Append(',').Append(r.y.ToString("R")).Append(',').Append(r.z.ToString("R")).Append(',').Append(r.w.ToString("R"))
          .Append("],\"scale\":[").Append(s.x.ToString("R")).Append(',').Append(s.y.ToString("R")).Append(',').Append(s.z.ToString("R"))
          .Append("],\"components\":\"").Append(comps).Append("\"}\n");
        for (var i = 0; i < t.childCount; i++) DumpHierarchy(t.GetChild(i), t.name, sb, stem);
    }

    private static void RunPipeline(string label, Func<Mod, Task> action)
    {
        var mod = AssetDatabase.LoadAssetAtPath<Mod>(ModAssetPath);
        if (mod == null)
        {
            Debug.LogError("[HumbleSpaceProgramBatch] Mod asset missing; run SetupMod first: " + ModAssetPath);
            Exit(1);
            return;
        }

        Task task;
        try
        {
            task = action(mod);
        }
        catch (Exception e)
        {
            Debug.LogError($"[HumbleSpaceProgramBatch] {label} threw synchronously: {e}");
            Exit(1);
            return;
        }

        // ThunderKit pipelines are async and resume on the editor loop, so poll from EditorApplication.update
        // and exit the (non -quit) batch editor when the task settles.
        var deadline = DateTime.UtcNow.AddMinutes(30);
        EditorApplication.CallbackFunction poll = null;
        poll = () =>
        {
            if (!task.IsCompleted)
            {
                if (DateTime.UtcNow < deadline) return;
                Debug.LogError($"[HumbleSpaceProgramBatch] {label} timed out after 30 minutes.");
                EditorApplication.update -= poll;
                Exit(1);
                return;
            }
            EditorApplication.update -= poll;
            if (task.IsFaulted)
            {
                Debug.LogError($"[HumbleSpaceProgramBatch] {label} failed: {task.Exception}");
                Exit(1);
                return;
            }
            Debug.Log($"[HumbleSpaceProgramBatch] {label} finished.");
            Exit(0);
        };
        EditorApplication.update += poll;
    }

    private static void Exit(int code)
    {
        AssetDatabase.SaveAssets();
        if (Application.isBatchMode)
        {
            EditorApplication.Exit(code);
        }
    }
}
