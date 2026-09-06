"""Shared path helpers for the KSP2 Redux install."""
import os
CANDIDATES = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Kerbal Space Program 2",
    r"C:\Program Files\Steam\steamapps\common\Kerbal Space Program 2",
    r"D:\SteamLibrary\steamapps\common\Kerbal Space Program 2",
]
def ksp_root():
    env = os.environ.get("KSP2_PATH")
    if env and os.path.isdir(env):
        return env
    for c in CANDIDATES:
        if os.path.isdir(c):
            return c
    raise SystemExit("KSP2 install not found; set KSP2_PATH")
def aa_dir(root=None):
    return os.path.join(root or ksp_root(), "KSP2_x64_Data", "StreamingAssets", "aa", "StandaloneWindows64")
def catalog(root=None):
    return os.path.join(root or ksp_root(), "KSP2_x64_Data", "StreamingAssets", "aa", "catalog.json")
def audio_dir(root=None):
    return os.path.join(root or ksp_root(), "KSP2_x64_Data", "StreamingAssets", "Audio", "GeneratedSoundBanks", "Windows")
