"""Address tables per Geometry Dash version (one JSON file per version in this folder).

Each table is selected by the executable's SHA-256 and verified by the in-game agent, which compares bytes
before using it. How to create a new table: docs/REVERSING.md.
"""
import json
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class VersionTable:
    gd_version: str
    platform: str
    exe_sha256: str
    data: dict

    @property
    def label(self) -> str:
        return '%s (%s)' % (self.gd_version, self.platform)

    def matches(self, sha256: str) -> bool:
        return sha256.lower().startswith(self.exe_sha256.lower())


def load_tables() -> list[VersionTable]:
    tables = []
    for f in sorted(resources.files(__package__).iterdir(), key=lambda p: p.name):
        if f.name.endswith('.json'):
            d = json.loads(f.read_text(encoding='utf-8'))
            tables.append(VersionTable(d['gd_version'], d['platform'], d['exe_sha256'], d))
    return tables


def find_table(sha256: str | None) -> VersionTable | None:
    if not sha256:
        return None
    return next((t for t in load_tables() if t.matches(sha256)), None)


def supported_versions() -> list[str]:
    return [t.label for t in load_tables()]
