import struct, sys, collections
p = sys.argv[1]
b = open(p,'rb').read()
off = 0
sections = {}
while off + 8 <= len(b):
    tag = b[off:off+4].decode('ascii','replace'); ln = struct.unpack_from('<I', b, off+4)[0]
    sections[tag] = (off+8, ln); off += 8 + ln
print('sections:', {k: v[1] for k, v in sections.items()})
if 'BKHD' in sections:
    o, l = sections['BKHD']; ver, bid = struct.unpack_from('<II', b, o); print(f'bank version {ver} id {bid}')
if 'DIDX' in sections:
    o, l = sections['DIDX']; n = l // 12
    print(f'embedded wems: {n}')
if 'STID' in sections:
    o, l = sections['STID']; t, n = struct.unpack_from('<II', b, o); q = o+8
    for i in range(n):
        bid = struct.unpack_from('<I', b, q)[0]; sl = b[q+4]; s = b[q+5:q+5+sl].decode(); q += 5+sl; print('  STID', bid, s)
if 'HIRC' in sections:
    o, l = sections['HIRC']; n = struct.unpack_from('<I', b, o)[0]; q = o+4
    types = collections.Counter(); events = []; sounds = []
    names = {1:'Settings',2:'Sound',3:'Action',4:'Event',5:'RandomSeq',6:'Switch',7:'ActorMixer',8:'Bus',9:'Layer',10:'MusicSegment',11:'MusicTrack',12:'MusicSwitch',13:'MusicPlaylist',14:'Attenuation',15:'DialogueEvent',16:'FxShareSet',17:'FxCustom',18:'AuxBus',19:'LFO',20:'Envelope',21:'AudioDevice',22:'TimeMod'}
    for i in range(n):
        t = b[q]; sz = struct.unpack_from('<I', b, q+1)[0]; oid = struct.unpack_from('<I', b, q+5)[0]
        types[names.get(t, str(t))] += 1
        if t == 4: events.append(oid)
        if t == 2:
            # Sound: after id: plugin info: 4 bytes plugin id, then stream type(1), source id(4)
            plug = struct.unpack_from('<I', b, q+9)[0]; stream = b[q+13]; src = struct.unpack_from('<I', b, q+14)[0]
            sounds.append((oid, src, stream))
        q += 5 + sz
    print('HIRC objects:', dict(types))
    print(f'event ids ({len(events)}):', events[:60], '...' if len(events) > 60 else '')
    print(f'sounds ({len(sounds)}): first 30 (soundId, wemSourceId, streamType):', sounds[:30])
