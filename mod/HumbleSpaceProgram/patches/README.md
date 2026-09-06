# Patch Manager patches

Lua text patches and Unity prefab patches go here (the SDK copies `Copied/patches` into the deployed
mod). Two candidates for this mod:

1. `eva_kerbal` part data: adjust `crashTolerance`, mass or the drag cube if the human model's
   collider volume changes noticeably. Example:

   ```lua
   PM.Parts:Patch("HumanEvaTolerance")
       :Named("eva_kerbal")
       :Do(function(part)
           part.crashTolerance = 30.0
       end)
   ```

2. Prefab patches (authored in Unity from a Linked Addressable of `eva_kerbal.prefab` or
   `KerbalWithControls.prefab`): swap collider sizes, camera pivots or particle anchors if the human
   silhouette differs from the kerbal one.

The `kerbal_variety` JSON tables are NOT patched here; they are overridden at runtime by
`Code/VarietyPatches.cs` (see that file for why).
