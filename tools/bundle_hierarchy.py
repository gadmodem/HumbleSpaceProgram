import sys, UnityPy
env = UnityPy.load(sys.argv[1])
maxdepth = int(sys.argv[2]) if len(sys.argv) > 2 else 99
tf = {}
for obj in env.objects:
    if obj.type.name in ('Transform',):
        t = obj.read_typetree()
        tf[obj.path_id] = t
go_name = {}
for obj in env.objects:
    if obj.type.name == 'GameObject':
        t = obj.read_typetree(); go_name[obj.path_id] = (t['m_Name'], [c.get('component', {}).get('m_PathID') for c in t.get('m_Component', [])])
comp_type = {obj.path_id: obj.type.name for obj in env.objects}
def name_of(tpid):
    t = tf[tpid]; gpid = t['m_GameObject']['m_PathID']; n, comps = go_name.get(gpid, ('?', []))
    extra = [comp_type.get(c) for c in comps if comp_type.get(c) not in ('Transform', None)]
    return n + ('  {' + ','.join(extra) + '}' if extra else '')
roots = [pid for pid, t in tf.items() if t['m_Father']['m_PathID'] == 0 or t['m_Father']['m_PathID'] not in tf]
def dump(pid, d):
    if d > maxdepth: return
    print('  ' * d + name_of(pid))
    for c in tf[pid]['m_Children']:
        if c['m_PathID'] in tf: dump(c['m_PathID'], d + 1)
for r in roots: dump(r, 0)
