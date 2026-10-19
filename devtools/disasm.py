"""Disassembles GeometryDash.exe functions (RVA), annotating calls (imports and binding names).

Usage: python devtools/disasm.py 0x1c8500 [n_instructions]
"""
import json, re, struct, sys
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
HERE = Path(__file__).resolve().parent
p = r"C:\Program Files (x86)\Steam\steamapps\common\Geometry Dash\GeometryDash.exe"
d = open(p, 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]; opt = pe + 24; optsize = struct.unpack_from('<H', d, pe + 20)[0]
secs = [struct.unpack_from('<8sIIII', d, opt + optsize + 40 * i) for i in range(nsec)]
iat = json.load(open(HERE / 'data' / 'iat.json')) if (HERE / 'data' / 'iat.json').exists() else {}
names = json.load(open(HERE / 'data' / 'names_2.2091.json')) if (HERE / 'data' / 'names_2.2091.json').exists() else {}
def off(rva):
    for n, vs, va, rs, ro in secs:
        if va <= rva < va + max(vs, rs): return rva - va + ro
def short(s):
    m = re.search(r'!\?(\w+)@(\w+)@', s)
    return (m.group(2) + '::' + m.group(1)) if m else s
rva = int(sys.argv[1], 16); n = int(sys.argv[2]) if len(sys.argv) > 2 else 60
md = Cs(CS_ARCH_X86, CS_MODE_64)
prev = None
for i, ins in enumerate(md.disasm(d[off(rva):off(rva) + 8000], rva)):
    if i >= n: break
    note = ''
    m = re.search(r'\[rip \+ (0x[0-9a-f]+)\]', ins.op_str)
    if m and ins.mnemonic in ('call', 'jmp'):
        note = short(iat.get(hex(ins.address + ins.size + int(m.group(1), 16)), ''))
    elif ins.mnemonic in ('call', 'jmp') and ins.op_str.startswith('0x'):
        note = names.get(ins.op_str, '')
    print('%8x  %-8s %-40s %s' % (ins.address, ins.mnemonic, ins.op_str, ('; ' + note) if note else ''))
    if ins.mnemonic == 'int3' and prev == 'int3': break
    prev = ins.mnemonic
