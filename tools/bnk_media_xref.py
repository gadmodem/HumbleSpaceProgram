import struct, sys, glob, os
def sections(b):
    off=0; s={}
    while off+8<=len(b):
        tag=b[off:off+4].decode('ascii','replace'); ln=struct.unpack_from('<I',b,off+4)[0]; s[tag]=(off+8,ln); off+=8+ln
    return s
def didx(path):
    b=open(path,'rb').read(); s=sections(b)
    if 'DIDX' not in s: return set()
    o,l=s['DIDX']; return {struct.unpack_from('<I',b,o+i*12)[0] for i in range(l//12)}
au=sys.argv[1]
voice=didx(os.path.join(au,'u_Kerbal_voice_media.bnk')); sfx=didx(os.path.join(au,'Kerbals_SFX_media.bnk'))
print('voice wems', len(voice), 'sfx wems', len(sfx))
for p in sorted(glob.glob(os.path.join(au,'*_events.bnk'))+[os.path.join(au,'u_states_UI_music_utilities_events.bnk')]):
    b=open(p,'rb').read(); s=sections(b)
    if 'HIRC' not in s: continue
    o,l=s['HIRC']; n=struct.unpack_from('<I',b,o)[0]; q=o+4; ev=[]; srcs=set()
    for i in range(n):
        t=b[q]; sz=struct.unpack_from('<I',b,q+1)[0]; oid=struct.unpack_from('<I',b,q+5)[0]
        if t==4: ev.append(oid)
        if t==2: srcs.add(struct.unpack_from('<I',b,q+14)[0])
        q+=5+sz
    v=len(srcs&voice); f=len(srcs&sfx)
    if v or f: print(f'{os.path.basename(p):45s} events={len(ev):4d} sounds->voiceMedia={v:3d} sounds->kerbalSFXMedia={f:3d}')
