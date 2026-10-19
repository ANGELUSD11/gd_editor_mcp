"""Finds the direct calls (E8 rel32) to a GeometryDash.exe function and the function that contains each one.

Usage: python devtools/xref.py 0x1c7490 [--exe PATH]
"""
import argparse
import struct
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep the project's single __pycache__ folder (see src/__init__.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe import PEImage, default_exe  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('rva')
    ap.add_argument('--exe', default=str(default_exe()))
    args = ap.parse_args()

    exe = PEImage(args.exe)
    target = int(args.rva, 16)
    _, va, _, raw, size = exe.section('.text')
    blob = exe.data[raw:raw + size]
    callers: dict = {}
    i = blob.find(b'\xe8')
    while i != -1:
        if i + 5 <= len(blob) and va + i + 5 + struct.unpack_from('<i', blob, i + 1)[0] == target:
            callers.setdefault(exe.function_containing(va + i), []).append(va + i)
        i = blob.find(b'\xe8', i + 1)
    for f, calls in callers.items():
        where = '%s-%s  (%d bytes)' % (hex(f[0]), hex(f[1]), f[1] - f[0]) if f else 'outside any known function'
        print('function %s calls at %s' % (where, [hex(c) for c in calls]))


if __name__ == '__main__':
    main()
