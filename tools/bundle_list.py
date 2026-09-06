import sys, re, collections
import UnityPy
path = sys.argv[1]
pat = re.compile(sys.argv[2], re.I) if len(sys.argv) > 2 else None
dump_text = len(sys.argv) > 3 and sys.argv[3] == 'text'
env = UnityPy.load(path)
counts = collections.Counter()
rows = []
for obj in env.objects:
    t = obj.type.name
    counts[t] += 1
    name = ''
    try:
        if t in ('GameObject','Mesh','Texture2D','Material','AnimationClip','AnimatorController','Avatar','Shader','TextAsset','MonoBehaviour','AudioClip','AnimatorOverrideController','SkinnedMeshRenderer','Transform','Sprite','Font'):
            d = obj.read()
            name = getattr(d, 'm_Name', '') or getattr(d, 'name', '') or ''
            if t == 'MonoBehaviour' and not name:
                try:
                    tree = obj.read_typetree()
                    name = tree.get('m_Name','') or ''
                except Exception: pass
            if t == 'Texture2D':
                name += f'  [{d.m_Width}x{d.m_Height} {d.m_TextureFormat.name if hasattr(d.m_TextureFormat,"name") else d.m_TextureFormat}]'
            if t == 'Mesh':
                try: name += f'  [verts={d.m_VertexData.m_VertexCount} submeshes={len(d.m_SubMeshes)} bones={len(d.m_BindPose)}]'
                except Exception: pass
            if t == 'AnimationClip':
                try: name += f'  [len={d.m_MuscleClipInfo.m_StopTime - d.m_MuscleClipInfo.m_StartTime:.2f}s]' 
                except Exception: pass
            if t == 'TextAsset' and dump_text and (pat is None or pat.search(name)):
                print(f'----- TextAsset {name} -----')
                s = d.m_Script if isinstance(d.m_Script, str) else d.m_Script.decode('utf-8','replace')
                print(s[:6000])
    except Exception as e:
        name = f'<err {e}>'
    if name and (pat is None or pat.search(name)):
        rows.append((t, name))
print('== type counts:', dict(counts))
for t, n in sorted(rows):
    print(f'{t:22s} {n}')
