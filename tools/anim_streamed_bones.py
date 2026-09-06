import sys, UnityPy, collections
env = UnityPy.load(sys.argv[1]); want = set(sys.argv[2:])
tos = {}
for obj in env.objects:
    if obj.type.name == 'AnimatorController':
        t = obj.read_typetree(); 
        for h, n in t.get('m_TOS', []): tos[h] = n
for obj in env.objects:
    if obj.type.name != 'AnimationClip': continue
    t = obj.read_typetree()
    for h, n in t.get('m_ClipBindingConstant', {}).get('pptrCurveMapping', []) or []: pass
# TOS from avatar in another bundle: pass names via second bundle path? simpler: hash->name from clip's own m_ClipBindingConstant has no names; use avatar bundle
av = UnityPy.load(sys.argv[2])
for obj in av.objects:
    if obj.type.name == 'Avatar':
        t = obj.read_typetree()
        for h, n in t['m_TOS']: tos[h] = n
agg = collections.Counter(); nclips = 0
for obj in env.objects:
    if obj.type.name != 'AnimationClip': continue
    t = obj.read_typetree(); name = t['m_Name']
    if not name.startswith('kerbal_'): continue
    data = t['m_MuscleClip']['m_Clip']['data']; n_stream = data['m_StreamedClip'].get('curveCount') or 0
    idx = 0; nclips += 1
    for b in t['m_ClipBindingConstant']['genericBindings']:
        attr = b['attribute']; typ = b.get('typeID'); size = {1:3,2:4,3:3,4:3}.get(attr, 1) if typ == 4 else 1
        if typ == 4 and attr == 1 and idx < n_stream:
            agg[tos.get(b['path'], str(b['path'])).split('/')[-1]] += 1
        idx += size
print('clips analysed:', nclips)
print('bones with ANIMATED (streamed) position curves, count of clips:')
for n, c in agg.most_common(): print(f'  {c:4d}  {n}')
