"""Collision geometry of a level: objects turned into boxes and circles the simulator can test against."""
import json
import math
from dataclasses import dataclass
from importlib import resources

BUCKET = 60.0
# Objects the simulator cannot model yet: if the cube gets near one, the simulation stops and says so.
UNSUPPORTED = {'slope', 'hazard_slope', 'pink_pad', 'red_pad', 'blue_pad', 'pink_orb', 'red_orb', 'blue_orb',
               'green_orb', 'black_orb', 'dash_orb', 'portal', 'unknown'}
IGNORED = {'ignore', 'cube_portal'}

_table: dict | None = None


def hitbox_table() -> dict:
    """{object id: {kind, shape, w, h, x, y | r}} (see devtools/build_hitboxes.py)."""
    global _table
    if _table is None:
        raw = json.loads((resources.files(__package__) / 'hitboxes.json').read_text(encoding='utf-8'))
        _table = {int(k): v for k, v in raw['objects'].items()}
    return _table


@dataclass
class Body:
    kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    oid: int
    ox: float              # object position, for reports
    oy: float
    r: float = 0.0         # circle radius (0 for boxes)

    @property
    def is_circle(self) -> bool:
        return self.r > 0

    def overlaps(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        if self.is_circle:
            cx, cy = (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2
            nx, ny = min(max(cx, x0), x1), min(max(cy, y0), y1)
            return (nx - cx) ** 2 + (ny - cy) ** 2 < self.r ** 2
        return x0 < self.x1 and x1 > self.x0 and y0 < self.y1 and y1 > self.y0

    def describe(self) -> dict:
        return {'id': self.oid, 'kind': self.kind, 'x': round(self.ox, 2), 'y': round(self.oy, 2)}


def _object_dict(obj: str) -> dict[str, str]:
    p = obj.split(',')
    return {p[i]: p[i + 1] for i in range(0, len(p) - 1, 2)}


def body_from_object(obj: str) -> Body | None:
    d = _object_dict(obj)
    try:
        oid = int(float(d.get('1', 0)))
        x, y = float(d.get('2', 0)), float(d.get('3', 0))
    except ValueError:
        return None
    entry = hitbox_table().get(oid)
    if entry is None or entry['kind'] in IGNORED or d.get('121') == '1':     # 121: "no touch"
        return None
    uniform = float(d.get('32', 1) or 1)
    sx, sy = float(d.get('128', uniform) or uniform), float(d.get('129', uniform) or uniform)
    if entry['shape'] == 'circle':
        r = entry['r'] * max(abs(sx), abs(sy))
        return Body(entry['kind'], x - r, y - r, x + r, y + r, oid, x, y, r)
    w, h = entry['w'] * abs(sx), entry['h'] * abs(sy)
    ox, oy = entry['x'] * sx, entry['y'] * sy
    if d.get('4') == '1':
        ox = -ox
    if d.get('5') == '1':
        oy = -oy
    angle = math.radians(float(d.get('6', 0) or 0))       # GD rotates clockwise, y points up
    c, s = math.cos(angle), math.sin(angle)
    ox, oy = ox * c + oy * s, -ox * s + oy * c
    bw, bh = abs(w * c) + abs(h * s), abs(w * s) + abs(h * c)   # bounding box of the rotated hitbox
    cx, cy = x + ox, y + oy
    return Body(entry['kind'], cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2, oid, x, y)


class World:
    def __init__(self, bodies: list[Body]):
        self.bodies = bodies
        self._buckets: dict[int, list[Body]] = {}
        for b in bodies:
            for k in range(int(b.x0 // BUCKET), int(b.x1 // BUCKET) + 1):
                self._buckets.setdefault(k, []).append(b)

    @classmethod
    def from_objects(cls, objects: list[str]) -> 'World':
        return cls([b for b in map(body_from_object, objects) if b is not None])

    def near(self, x0: float, x1: float) -> list[Body]:
        seen, out = set(), []
        for k in range(int(x0 // BUCKET), int(x1 // BUCKET) + 1):
            for b in self._buckets.get(k, ()):
                if id(b) not in seen:
                    seen.add(id(b))
                    out.append(b)
        return out

    def speed_portals(self) -> list[tuple[float, str]]:
        """(touch x, speed) of the speed portals, in the format levels.timing.Timeline expects."""
        return [(b.x0 - 15.0, b.kind[len('speed_'):]) for b in self.bodies if b.kind.startswith('speed_')]
