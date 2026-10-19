"""Disassembles a GeometryDash.exe function, annotating calls with import names and binding names.

Usage: python devtools/disasm.py 0x1c8500 [n_instructions] [--exe PATH] [--version 2.2091]
Annotations come from devtools/data (see build_data.py); --version defaults to the executable's table version.
"""
import argparse
import re
import sys
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_64, Cs

sys.dont_write_bytecode = True  # keep the project's single __pycache__ folder (see src/__init__.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe import PEImage, default_exe, detect_version, load_data  # noqa: E402


def short(name: str) -> str:
    m = re.search(r'!\?(\w+)@(\w+)@', name)
    return (m.group(2) + '::' + m.group(1)) if m else name


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('rva')
    ap.add_argument('count', nargs='?', type=int, default=60)
    ap.add_argument('--exe', default=str(default_exe()))
    ap.add_argument('--version')
    args = ap.parse_args()

    exe = PEImage(args.exe)
    version = args.version or detect_version(exe)
    iat, names = load_data('iat', version), load_data('names', version)
    rva = int(args.rva, 16)
    prev = None
    for i, ins in enumerate(Cs(CS_ARCH_X86, CS_MODE_64).disasm(exe.read(rva, 8000), rva)):
        if i >= args.count:
            break
        note = ''
        m = re.search(r'\[rip \+ (0x[0-9a-f]+)\]', ins.op_str)
        if m and ins.mnemonic in ('call', 'jmp'):
            note = short(iat.get(hex(ins.address + ins.size + int(m.group(1), 16)), ''))
        elif ins.mnemonic in ('call', 'jmp') and ins.op_str.startswith('0x'):
            note = names.get(ins.op_str, '')
        print('%8x  %-8s %-40s %s' % (ins.address, ins.mnemonic, ins.op_str, ('; ' + note) if note else ''))
        if ins.mnemonic == 'int3' and prev == 'int3':
            break
        prev = ins.mnemonic


if __name__ == '__main__':
    main()
