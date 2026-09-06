import json, base64, struct, sys, re
path = sys.argv[1]
pat = re.compile(sys.argv[2], re.I)
with open(path, 'rb') as f:
    cat = json.load(f)
data = base64.b64decode(cat['m_KeyDataString'])
n = struct.unpack_from('<i', data, 0)[0]
off = 4
keys = []
for i in range(n):
    t = data[off]; off += 1
    if t == 0:  # ASCII
        l = struct.unpack_from('<i', data, off)[0]; off += 4
        keys.append(data[off:off+l].decode('ascii', 'replace')); off += l
    elif t == 1:  # UTF16
        l = struct.unpack_from('<i', data, off)[0]; off += 4
        keys.append(data[off:off+l].decode('utf-16-le', 'replace')); off += l
    elif t == 2:  # UInt16
        keys.append(struct.unpack_from('<H', data, off)[0]); off += 2
    elif t == 3:  # UInt32
        keys.append(struct.unpack_from('<I', data, off)[0]); off += 4
    elif t == 4:  # Int32
        keys.append(struct.unpack_from('<i', data, off)[0]); off += 4
    elif t == 5:  # Hash128
        keys.append('hash:'+data[off:off+16].hex()); off += 16
    elif t == 6:  # Type
        l = struct.unpack_from('<i', data, off)[0]; off += 4
        keys.append('type:'+data[off:off+l].decode('ascii','replace')); off += l
    elif t == 7:  # JsonObject
        al = data[off]; off += 1; an = data[off:off+al].decode(); off += al
        tl = data[off]; off += 1; tn = data[off:off+tl].decode(); off += tl
        jl = struct.unpack_from('<i', data, off)[0]; off += 4
        keys.append('json:'+tn); off += jl
    else:
        keys.append(f'?{t}')
strs = [k for k in keys if isinstance(k, str) and pat.search(k)]
print(f"total keys: {n}; matching: {len(strs)}")
for k in sorted(set(strs)):
    print(k)
