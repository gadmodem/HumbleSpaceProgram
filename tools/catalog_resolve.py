import json, base64, struct, sys, re
path = sys.argv[1]; pat = re.compile(sys.argv[2], re.I)
cat = json.load(open(path, 'rb'))
def read_keys(blob):
    data = base64.b64decode(blob); n = struct.unpack_from('<i', data, 0)[0]; off = 4; keys = []
    for i in range(n):
        t = data[off]; off += 1
        if t in (0, 1):
            l = struct.unpack_from('<i', data, off)[0]; off += 4
            keys.append(data[off:off+l].decode('ascii' if t == 0 else 'utf-16-le', 'replace')); off += l
        elif t == 2: keys.append(struct.unpack_from('<H', data, off)[0]); off += 2
        elif t in (3, 4): keys.append(struct.unpack_from('<I', data, off)[0]); off += 4
        elif t == 5: keys.append('hash:' + data[off:off+16].hex()); off += 16
        elif t == 6:
            l = struct.unpack_from('<i', data, off)[0]; off += 4; keys.append('type:' + data[off:off+l].decode('ascii', 'replace')); off += l
        elif t == 7:
            al = data[off]; off += 1; off += al; tl = data[off]; off += 1; tn = data[off:off+tl].decode(); off += tl
            jl = struct.unpack_from('<i', data, off)[0]; off += 4; keys.append('json:' + tn); off += jl
        else: keys.append(f'?{t}')
    return keys
keys = read_keys(cat['m_KeyDataString'])
bucket = base64.b64decode(cat['m_BucketDataString'])
nb = struct.unpack_from('<i', bucket, 0)[0]; off = 4; buckets = []
for i in range(nb):
    doff = struct.unpack_from('<i', bucket, off)[0]; off += 4
    ne = struct.unpack_from('<i', bucket, off)[0]; off += 4
    ents = list(struct.unpack_from('<%di' % ne, bucket, off)); off += 4 * ne
    buckets.append((doff, ents))
entry = base64.b64decode(cat['m_EntryDataString'])
ne = struct.unpack_from('<i', entry, 0)[0]; off = 4; entries = []
for i in range(ne):
    vals = struct.unpack_from('<7i', entry, off); off += 28
    entries.append(vals)  # internalId, providerIndex, dependencyKeyIndex, depHash, dataIndex, primaryKey, resourceType
iids = cat['m_InternalIds']; provs = cat['m_ProviderIds']; rtypes = cat['m_resourceTypes']
for ki, k in enumerate(keys):
    if not isinstance(k, str) or not pat.search(k): continue
    for ei in buckets[ki][1]:
        iid, pidx, depkey, deph, didx, pk, rt = entries[ei]
        dep = keys[depkey] if depkey >= 0 else None
        depbundles = []
        if depkey >= 0:
            for dei in buckets[depkey][1]:
                depbundles.append(iids[entries[dei][0]].split('/')[-1])
        print(f'{k}\n    internalId={iids[iid]}\n    provider={provs[pidx].split(".")[-1]} type={rtypes[rt]["m_ClassName"].split(".")[-1]}\n    depKey={dep}\n    bundles={depbundles[:6]}')
