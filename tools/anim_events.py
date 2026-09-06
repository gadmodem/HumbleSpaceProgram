import sys, collections, UnityPy
env = UnityPy.load(sys.argv[1])
names = collections.Counter(); per = {}
for obj in env.objects:
    if obj.type.name != 'AnimationClip': continue
    try:
        t = obj.read_typetree()
    except Exception as e: continue
    evs = t.get('m_Events', [])
    for e in evs:
        fn = e.get('functionName',''); s = e.get('data','') or e.get('stringParameter','')
        names[(fn, s)] += 1
        per.setdefault(t.get('m_Name'), []).append((fn, s))
print('distinct (function, string):')
for (fn, s), c in sorted(names.items(), key=lambda x: -x[1]): print(f'  {c:4d} {fn}  {s}')
print('\nclips with events:', len(per))
