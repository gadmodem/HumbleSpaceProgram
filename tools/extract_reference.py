"""Extract kerbal reference assets (meshes, textures, materials, rig hierarchy, animation list)
from the stock Addressables bundles into ./reference.

Run from the project root with the tools venv:

    tools\\venv\\Scripts\\python tools\\extract_reference.py

Extracted files are stock game assets: keep them local (reference/ is git-ignored) and never
redistribute them inside the mod.
"""
import os, sys, json, base64, struct
sys.path.insert(0, os.path.dirname(__file__))
import ksp2paths
import UnityPy

ROOT = ksp2paths.ksp_root()
AA = ksp2paths.aa_dir(ROOT)
CAT = ksp2paths.catalog(ROOT)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reference")

PREFAB_KEYS = [
    "head_m_01.prefab", "head_f_01.prefab", "eyes_m_01.prefab", "eyes_f_01.prefab",
    "body_spacesuit_01.prefab", "body_jumpsuit_01.prefab", "helm_spacesuit_01.prefab",
    "hair_m_01.prefab", "hair_f_01.prefab", "facialhair_fullbeard.prefab", "eva_kerbal.prefab",
    "KerbalWithControls.prefab", "kerbalIVA.prefab",
]


def read_keys(blob):
    data = base64.b64decode(blob)
    n = struct.unpack_from('<i', data, 0)[0]
    off = 4
    keys = []
    for _ in range(n):
        t = data[off]
        off += 1
        if t in (0, 1):
            l = struct.unpack_from('<i', data, off)[0]
            off += 4
            keys.append(data[off:off + l].decode('ascii' if t == 0 else 'utf-16-le', 'replace'))
            off += l
        elif t == 2:
            keys.append(struct.unpack_from('<H', data, off)[0])
            off += 2
        elif t in (3, 4):
            keys.append(struct.unpack_from('<I', data, off)[0])
            off += 4
        elif t == 5:
            keys.append('hash:' + data[off:off + 16].hex())
            off += 16
        elif t == 6:
            l = struct.unpack_from('<i', data, off)[0]
            off += 4
            keys.append('type:' + data[off:off + l].decode('ascii', 'replace'))
            off += l
        elif t == 7:
            al = data[off]
            off += 1 + al
            tl = data[off]
            off += 1 + tl
            jl = struct.unpack_from('<i', data, off)[0]
            off += 4
            keys.append('json')
            off += jl
        else:
            keys.append(None)
    return keys


def resolve_bundles(keys_wanted):
    """Map addressable key -> list of bundle file names (primary bundle first)."""
    cat = json.load(open(CAT, 'rb'))
    keys = read_keys(cat['m_KeyDataString'])
    bucket = base64.b64decode(cat['m_BucketDataString'])
    nb = struct.unpack_from('<i', bucket, 0)[0]
    off = 4
    buckets = []
    for _ in range(nb):
        off += 4
        ne = struct.unpack_from('<i', bucket, off)[0]
        off += 4
        buckets.append(list(struct.unpack_from('<%di' % ne, bucket, off)))
        off += 4 * ne
    entry = base64.b64decode(cat['m_EntryDataString'])
    ne = struct.unpack_from('<i', entry, 0)[0]
    off = 4
    entries = []
    for _ in range(ne):
        entries.append(struct.unpack_from('<7i', entry, off))
        off += 28
    iids = cat['m_InternalIds']
    result = {}
    for ki, k in enumerate(keys):
        if k not in keys_wanted:
            continue
        for ei in buckets[ki]:
            depkey = entries[ei][2]
            bl = []
            if depkey >= 0:
                for dei in buckets[depkey]:
                    bl.append(iids[entries[dei][0]].replace('\\', '/').split('/')[-1])
            result[k] = bl
    return result


def hierarchy(env):
    tf = {o.path_id: o.read_typetree() for o in env.objects if o.type.name == 'Transform'}
    go = {}
    ctype = {o.path_id: o.type.name for o in env.objects}
    for o in env.objects:
        if o.type.name == 'GameObject':
            t = o.read_typetree()
            go[o.path_id] = (t['m_Name'], [c.get('component', {}).get('m_PathID') for c in t.get('m_Component', [])])

    def node(pid):
        t = tf[pid]
        name, comps = go.get(t['m_GameObject']['m_PathID'], ('?', []))
        lp, lr, ls = t['m_LocalPosition'], t['m_LocalRotation'], t['m_LocalScale']
        return {
            'name': name,
            'components': [ctype.get(c) for c in comps if ctype.get(c) not in ('Transform', None)],
            'localPosition': [lp['x'], lp['y'], lp['z']],
            'localRotation': [lr['x'], lr['y'], lr['z'], lr['w']],
            'localScale': [ls['x'], ls['y'], ls['z']],
            'children': [node(c['m_PathID']) for c in t['m_Children'] if c['m_PathID'] in tf],
        }

    roots = [pid for pid, t in tf.items() if t['m_Father']['m_PathID'] not in tf]
    return [node(r) for r in roots]


def export_bundle(path, outdir, seen):
    env = UnityPy.load(path)
    n = 0
    for obj in env.objects:
        if obj.type.name == 'Mesh':
            d = obj.read()
            name = d.m_Name
            if name in seen:
                continue
            try:
                with open(os.path.join(outdir, 'meshes', f'{name}.obj'), 'w') as f:
                    f.write(d.export())
                seen.add(name)
                n += 1
            except Exception as e:
                print('  mesh export failed', name, e)
        elif obj.type.name == 'Texture2D':
            d = obj.read()
            name = d.m_Name
            if name in seen:
                continue
            try:
                d.image.save(os.path.join(outdir, 'textures', f'{name}.png'))
                seen.add(name)
                n += 1
            except Exception as e:
                print('  texture export failed', name, e)
        elif obj.type.name == 'Material':
            t = obj.read_typetree()
            name = t['m_Name']
            if ('mat:' + name) in seen:
                continue
            sp = t.get('m_SavedProperties', {})
            mat = {
                'name': name,
                'textures': {k: v.get('m_Texture', {}).get('m_PathID') for k, v in sp.get('m_TexEnvs', [])},
                'floats': dict(sp.get('m_Floats', [])),
                'colors': {k: v for k, v in sp.get('m_Colors', [])},
            }
            with open(os.path.join(outdir, 'materials', f'{name}.json'), 'w') as f:
                json.dump(mat, f, indent=1)
            seen.add('mat:' + name)
            n += 1
    return n


def main():
    for sub in ('meshes', 'textures', 'materials', 'hierarchies', 'animation'):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    deps = resolve_bundles(set(PREFAB_KEYS))
    seen = set()
    all_bundles = []
    for k in PREFAB_KEYS:
        bl = deps.get(k, [])
        print(f'{k}: {len(bl)} bundles')
        if bl and os.path.exists(os.path.join(AA, bl[0])):
            env = UnityPy.load(os.path.join(AA, bl[0]))
            with open(os.path.join(OUT, 'hierarchies', k.replace('.prefab', '') + '.json'), 'w') as f:
                json.dump(hierarchy(env), f, indent=1)
        for b in bl:
            if b not in all_bundles:
                all_bundles.append(b)
    all_bundles.append('kerbal_shared_assets_all.bundle')
    for b in all_bundles:
        p = os.path.join(AA, b)
        if not os.path.exists(p) or 'unitybuiltinshaders' in b:
            continue
        n = export_bundle(p, OUT, seen)
        print(f'  {b}: exported {n}')

    # Animation clip list with animation events (sound hooks).
    env = UnityPy.load(os.path.join(AA, 'kerbal_shared_assets_all.bundle'))
    clips = []
    for obj in env.objects:
        if obj.type.name != 'AnimationClip':
            continue
        t = obj.read_typetree()
        mc = t['m_MuscleClip']
        clips.append({
            'name': t['m_Name'],
            'length': mc.get('m_StopTime', 0) - mc.get('m_StartTime', 0),
            'loop': bool(mc.get('m_LoopTime')),
            'events': [{'time': e.get('time'), 'function': e.get('functionName'), 'string': e.get('data')}
                       for e in t.get('m_Events', [])],
        })
    clips.sort(key=lambda c: c['name'])
    with open(os.path.join(OUT, 'animation', 'kerbal_clips.json'), 'w') as f:
        json.dump(clips, f, indent=1)
    print('clips:', len(clips))
    print('done ->', OUT)


if __name__ == '__main__':
    main()
