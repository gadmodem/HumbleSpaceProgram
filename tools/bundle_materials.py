import sys, UnityPy
for path in sys.argv[1:]:
    env = UnityPy.load(path)
    for obj in env.objects:
        if obj.type.name == 'Shader':
            try:
                t = obj.read_typetree(); print('SHADER:', t.get('m_ParsedForm', {}).get('m_Name'))
            except Exception as e: print('shader err', e)
        if obj.type.name == 'Material':
            t = obj.read_typetree(); print('MATERIAL:', t['m_Name'])
            sp = t.get('m_SavedProperties', {})
            for k, v in sp.get('m_TexEnvs', []): 
                tex = v.get('m_Texture', {}); print('   tex ', k, '-> fileID', tex.get('m_FileID'), 'pathID', tex.get('m_PathID'))
            for k, v in sp.get('m_Floats', []): print('   float', k, '=', v)
            for k, v in sp.get('m_Colors', []): print('   color', k, '=', v)
            print('   keywords:', t.get('m_ValidKeywords') or t.get('m_ShaderKeywords'))
