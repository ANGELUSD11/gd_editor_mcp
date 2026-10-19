"""Finds direct calls (E8 rel32) to an RVA and the function (.pdata) that contains each one.

Usage: python devtools/xref.py 0x1c7490
"""
import struct, sys, bisect
p = r"C:\Program Files (x86)\Steam\steamapps\common\Geometry Dash\GeometryDash.exe"
d = open(p, 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]; opt = pe + 24; optsize = struct.unpack_from('<H', d, pe + 20)[0]
secs = [struct.unpack_from('<8sIIII', d, opt + optsize + 40 * i) for i in range(nsec)]
def off(rva):
    for n, vs, va, rs, ro in secs:
        if va <= rva < va + max(vs, rs): return rva - va + ro
text = [s for s in secs if s[0].startswith(b'.text')][0]
pdata_rva, pdata_size = struct.unpack_from('<II', d, opt + 112 + 8 * 3)
o = off(pdata_rva)
funcs = sorted(struct.unpack_from('<II', d, o + 12 * i) for i in range(pdata_size // 12))
starts = [f[0] for f in funcs]
def owner(rva):
    i = bisect.bisect_right(starts, rva) - 1
    return funcs[i] if i >= 0 and funcs[i][0] <= rva < funcs[i][1] else None
target = int(sys.argv[1], 16)
va, ro, rs = text[2], text[4], text[3]
blob = d[ro:ro + rs]
res = {}
i = blob.find(b'\xe8')
while i != -1:
    rel = struct.unpack_from('<i', blob, i + 1)[0] if i + 5 <= len(blob) else None
    if rel is not None and va + i + 5 + rel == target:
        f = owner(va + i)
        res.setdefault(f, []).append(va + i)
    i = blob.find(b'\xe8', i + 1)
for f, calls in res.items():
    print('function %s-%s  (%d bytes) calls at %s' % (hex(f[0]), hex(f[1]), f[1] - f[0], [hex(c) for c in calls]))
