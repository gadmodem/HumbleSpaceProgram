import sys, os, json, glob, UnityPy
aa = sys.argv[1]; out = sys.argv[2]; maxsize = int(sys.argv[3])
refs = {}
files = [p for p in glob.glob(os.path.join(aa, '*.bundle')) if os.path.getsize(p) <= maxsize]
print('scanning', len(files), 'bundles'); sys.stdout.flush()
for i, p in enumerate(files):
    try:
        env = UnityPy.load(p)
        for obj in env.objects:
            if obj.type.name != 'MonoBehaviour': continue
            try: t = obj.read_typetree()
            except Exception: continue
            if 'objectName' in t and 'id' in t and 'guid' in t:
                refs[t['objectName']] = {'id': t['id'], 'guid': t['guid'], 'bundle': os.path.basename(p), 'kind': t.get('m_Name','')}
    except Exception as e:
        pass
    if i % 200 == 0: print(i, len(refs)); sys.stdout.flush()
json.dump(refs, open(out, 'w'), indent=1)
print('done refs:', len(refs))
