"""Shared helpers for the reverse engineering tools: reading GeometryDash.exe (PE64) and the per-version data files."""
import bisect
import hashlib
import json
import os
import struct
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
DEFAULT_EXE = r'C:\Program Files (x86)\Steam\steamapps\common\Geometry Dash\GeometryDash.exe'


def default_exe() -> Path:
    return Path(os.environ.get('GD_EXE', DEFAULT_EXE))


class PEImage:
    """Sections, imports and function table (.pdata) of a 64-bit Windows executable. Addresses are RVAs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise SystemExit('Executable not found: %s (use --exe or the GD_EXE variable)' % self.path)
        self.data = self.path.read_bytes()
        d = self.data
        pe = struct.unpack_from('<I', d, 0x3c)[0]
        if d[pe:pe + 4] != b'PE\0\0':
            raise SystemExit('%s is not a PE executable' % self.path)
        n_sections = struct.unpack_from('<H', d, pe + 6)[0]
        self.opt = pe + 24
        opt_size = struct.unpack_from('<H', d, pe + 20)[0]
        self.image_base = struct.unpack_from('<Q', d, self.opt + 24)[0]
        self.sections = []
        for i in range(n_sections):
            name, vsize, va, rsize, raw = struct.unpack_from('<8sIIII', d, self.opt + opt_size + 40 * i)
            self.sections.append((name.rstrip(b'\0').decode(), va, max(vsize, rsize), raw, rsize))
        self._functions = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def section(self, name: str):
        return next(s for s in self.sections if s[0] == name)

    def offset(self, rva: int) -> int:
        for _, va, size, raw, _ in self.sections:
            if va <= rva < va + size:
                return rva - va + raw
        raise ValueError('RVA %#x is outside the image' % rva)

    def read(self, rva: int, n: int) -> bytes:
        o = self.offset(rva)
        return self.data[o:o + n]

    def _directory(self, index: int) -> tuple[int, int]:
        return struct.unpack_from('<II', self.data, self.opt + 112 + 8 * index)

    def _cstr(self, rva: int) -> str:
        o = self.offset(rva)
        return self.data[o:self.data.index(b'\0', o)].decode()

    def imports(self) -> dict[int, str]:
        """{IAT slot RVA: "dll!function"} for imports by name."""
        out = {}
        rva, _ = self._directory(1)
        o = self.offset(rva)
        while True:
            lookup, _, _, name_rva, iat = struct.unpack_from('<IIIII', self.data, o)
            if not name_rva:
                break
            dll = self._cstr(name_rva)
            table = self.offset(lookup or iat)
            i = 0
            while True:
                entry = struct.unpack_from('<Q', self.data, table + 8 * i)[0]
                if not entry:
                    break
                if not entry >> 63:
                    out[iat + 8 * i] = '%s!%s' % (dll, self._cstr((entry & 0x7fffffff) + 2))
                i += 1
            o += 20
        return out

    def functions(self) -> list[tuple[int, int]]:
        """(start, end) of every function in the exception table (.pdata), sorted."""
        if self._functions is None:
            rva, size = self._directory(3)
            o = self.offset(rva)
            self._functions = sorted(struct.unpack_from('<II', self.data, o + 12 * i) for i in range(size // 12))
            self._starts = [f[0] for f in self._functions]
        return self._functions

    def function_containing(self, rva: int) -> tuple[int, int] | None:
        funcs = self.functions()
        i = bisect.bisect_right(self._starts, rva) - 1
        return funcs[i] if i >= 0 and funcs[i][0] <= rva < funcs[i][1] else None

    def is_function_start(self, rva: int) -> bool:
        self.functions()
        i = bisect.bisect_left(self._starts, rva)
        return i < len(self._starts) and self._starts[i] == rva


def detect_version(exe: PEImage) -> str | None:
    """GD version of an executable, from the server's version tables (None if it has no table yet)."""
    try:
        from gd_editor_mcp.versions import find_table
    except ImportError:
        return None
    table = find_table(exe.sha256)
    return table.gd_version if table else None


def data_file(kind: str, version: str) -> Path:
    return DATA / ('%s_%s.json' % (kind, version))


def load_data(kind: str, version: str | None) -> dict:
    """Reads data/<kind>_<version>.json; without a version, the newest one available."""
    if version is None:
        files = sorted(DATA.glob('%s_*.json' % kind))
        if not files:
            return {}
        path = files[-1]
    else:
        path = data_file(kind, version)
        if not path.exists():
            return {}
    return json.loads(path.read_text(encoding='utf-8'))
