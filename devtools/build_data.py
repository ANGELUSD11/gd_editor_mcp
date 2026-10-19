"""Builds the annotation data that disasm.py uses for a Geometry Dash version.

Writes devtools/data/iat_<version>.json (import slots of the executable) and devtools/data/names_<version>.json
(Windows addresses of geode-sdk/bindings, "Class::method"). It also reports how many binding addresses are real
function starts in the executable, a quick check that the bindings match it.

Usage: python devtools/build_data.py [--exe PATH] [--version 2.2091] [--bindings PATH_OR_URL]
  --version  defaults to the version of the server table that matches the executable
  --bindings defaults to bindings/<version>/GeometryDash.bro on the geode-sdk/bindings main branch
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True  # keep the project's single __pycache__ folder (see src/__init__.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe import DATA, PEImage, data_file, default_exe, detect_version  # noqa: E402

BINDINGS_URL = 'https://raw.githubusercontent.com/geode-sdk/bindings/main/bindings/%s/GeometryDash.bro'
CLASS_RE = re.compile(r'^class (\w+)')
METHOD_RE = re.compile(r'([~\w]+)\s*\(.*\)\s*(?:const\s*)?=\s*(.*)')
WIN_RE = re.compile(r'\bwin (0x[0-9a-fA-F]+)')
PLACEHOLDER = 0x9999999      # the bindings use it for "unknown address"


def read_bindings(source: str) -> str:
    if re.match(r'https?://', source):
        try:
            with urllib.request.urlopen(source, timeout=60) as r:
                return r.read().decode('utf-8')
        except OSError as e:
            raise SystemExit('Could not download the bindings (%s): %s\nPass a local file with --bindings.' % (source, e))
    return Path(source).read_text(encoding='utf-8')


def binding_names(text: str) -> dict[int, str]:
    """{RVA: "Class::method"} for every method with a Windows address."""
    names: dict[int, str] = {}
    cls = None
    for line in text.splitlines():
        if line.lstrip().startswith('//'):
            continue
        m = CLASS_RE.match(line)
        if m:
            cls = m.group(1)
            continue
        m = METHOD_RE.search(line)
        if not (m and cls):
            continue
        w = WIN_RE.search(m.group(2))
        if w:
            rva = int(w.group(1), 16)
            if rva != PLACEHOLDER:
                names.setdefault(rva, '%s::%s' % (cls, m.group(1)))
    return names


def check_addresses(exe: PEImage, names: dict[int, str]) -> tuple[int, list[tuple[int, str]]]:
    """How many addresses look like function starts, and the ones that fall inside another function.

    A start is either a .pdata entry or a leaf function: 16-byte aligned, preceded by padding (int3/ret/nop),
    outside every .pdata function (leaf functions have no unwind data).
    """
    good, inside = 0, []
    for rva, name in sorted(names.items()):
        if exe.is_function_start(rva):
            good += 1
        elif exe.function_containing(rva) is not None:
            inside.append((rva, name))
        else:
            try:
                good += rva % 16 == 0 and exe.read(rva - 1, 1)[0] in (0xcc, 0xc3, 0x90)
            except ValueError:
                pass
    return good, inside


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--exe', default=str(default_exe()))
    ap.add_argument('--version')
    ap.add_argument('--bindings')
    args = ap.parse_args()

    exe = PEImage(args.exe)
    version = args.version or detect_version(exe)
    if version is None:
        raise SystemExit('This executable has no version table yet: give its version with --version.')
    names = binding_names(read_bindings(args.bindings or BINDINGS_URL % version))
    imports = exe.imports()

    DATA.mkdir(exist_ok=True)
    data_file('iat', version).write_text(json.dumps({hex(k): v for k, v in sorted(imports.items())}, indent=0),
                                         encoding='utf-8')
    data_file('names', version).write_text(json.dumps({hex(k): v for k, v in sorted(names.items())}, indent=0),
                                           encoding='utf-8')

    good, inside = check_addresses(exe, names)
    print('GD %s  (%s, sha256 %s...)' % (version, exe.path, exe.sha256[:16]))
    print('  %-28s %5d import slots' % (data_file('iat', version).name, len(imports)))
    print('  %-28s %5d binding addresses, %d look like function starts (%.1f%%)'
          % (data_file('names', version).name, len(names), good, 100.0 * good / max(1, len(names))))
    if inside:
        print('  %d addresses fall inside another function (probably wrong in the bindings):' % len(inside))
        for rva, name in inside[:15]:
            print('    %#x  %s' % (rva, name))
    if names and good < 0.95 * len(names):
        print('  Warning: many addresses are not function starts; the bindings may not match this executable.')


if __name__ == '__main__':
    main()
