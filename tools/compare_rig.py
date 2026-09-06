"""Compare the bone transforms of an imported Unity model (logs/unity_prefab_hierarchies.jsonl, written
by HumbleSpaceProgramBatch.ImportModels) against the stock body prefab (reference/hierarchies/body_spacesuit_01.json).

    python tools/compare_rig.py [model_stem]

Reports bones missing on either side and any local position/rotation mismatch above tolerance.
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
stem = sys.argv[1] if len(sys.argv) > 1 else "body_human_spacesuit_01"

stock = {}
def walk(n, parent):
    if n["name"].startswith("bone_"):
        stock[n["name"]] = (parent, n["localPosition"], n["localRotation"], n["localScale"])
    for c in n["children"]:
        walk(c, n["name"])
for r in json.load(open(os.path.join(ROOT, "reference", "hierarchies", "body_spacesuit_01.json"))):
    walk(r, r["name"])

ours = {}
for line in open(os.path.join(ROOT, "logs", "unity_prefab_hierarchies.jsonl"), encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    j = json.loads(line)
    if j["model"] == stem and j["name"].startswith("bone_"):
        ours[j["name"]] = (j["parent"], j["pos"], j["rot"], j["scale"])

print(f"stock bones: {len(stock)}  imported bones ({stem}): {len(ours)}")
missing = sorted(set(stock) - set(ours)); extra = sorted(set(ours) - set(stock))
if missing: print("MISSING in import:", missing)
if extra: print("EXTRA in import:", extra)

def qdiff(a, b):
    # angle between quaternions, degrees
    d = abs(sum(x * y for x, y in zip(a, b)))
    d = max(-1.0, min(1.0, d))
    return math.degrees(2 * math.acos(d))

bad = 0
worst_pos = (0, None); worst_rot = (0, None)
for name in sorted(set(stock) & set(ours)):
    sp, sq, ss = stock[name][1], stock[name][2], stock[name][3]
    op, oq, os_ = ours[name][1], ours[name][2], ours[name][3]
    dp = math.dist(sp, op); dr = qdiff(sq, oq); ds = math.dist(ss, os_)
    if dp > worst_pos[0]: worst_pos = (dp, name)
    if dr > worst_rot[0]: worst_rot = (dr, name)
    if dp > 1e-3 or dr > 0.5 or ds > 1e-3:
        bad += 1
        if bad <= 15:
            print(f"  {name:34s} dpos={dp:.4f} drot={dr:6.2f}deg dscale={ds:.3f}  stock pos={[round(v,4) for v in sp]} ours={[round(v,4) for v in op]}")
    if stock[name][0] != ours[name][0] and name != "bone_kerbal_master_parent":
        print(f"  parent differs for {name}: stock {stock[name][0]} vs ours {ours[name][0]}")
print(f"mismatched bones: {bad}; worst position delta {worst_pos[0]:.4f} ({worst_pos[1]}), worst rotation delta {worst_rot[0]:.2f} deg ({worst_rot[1]})")
print("RESULT:", "MATCH" if bad == 0 and not missing else "MISMATCH")
