import sys
def fnv1_32(s):
    h = 2166136261
    for b in s.lower().encode():
        h = (h * 16777619) & 0xffffffff
        h ^= b
    return h
ids = set(int(x) for x in sys.argv[1].split(','))
for name in sys.argv[2:]:
    h = fnv1_32(name); print(('MATCH ' if h in ids else '      ') + f'{h:>11} {name}')
