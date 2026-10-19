"""Finds the game process and identifies its version by the executable hash."""
import hashlib
from dataclasses import dataclass
from pathlib import Path

import frida

EXE_NAME = 'GeometryDash.exe'
_hash_cache: dict[tuple, str] = {}


@dataclass(frozen=True)
class GameProcess:
    pid: int
    path: str | None
    sha256: str | None


def file_sha256(path: str) -> str:
    st = Path(path).stat()
    key = (path, st.st_size, st.st_mtime_ns)
    if key not in _hash_cache:
        _hash_cache[key] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return _hash_cache[key]


def find_game_process() -> GameProcess | None:
    for p in frida.get_local_device().enumerate_processes(scope='full'):
        if p.name.lower() == EXE_NAME.lower():
            path = p.parameters.get('path')
            return GameProcess(p.pid, path, file_sha256(path) if path else None)
    return None
