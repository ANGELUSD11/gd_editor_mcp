"""Objects of a level string: "1,<id>,2,<x>,3,<y>,<key>,<value>,..." separated by ";"."""
import re
from dataclasses import dataclass


def split_objects(text: str) -> list[str]:
    return [o.strip() for o in re.split(r'[;\n]+', text) if o.strip()]


def join_objects(objects: list[str]) -> str:
    return ''.join(o + ';' for o in objects)


def _fmt(v: float) -> str:
    s = ('%.3f' % v).rstrip('0').rstrip('.')
    return '0' if s in ('', '-0') else s


def shift_object(obj: str, dx: float = 0.0, dy: float = 0.0) -> str:
    """Offsets keys 2 (x) and 3 (y) of an object."""
    p = obj.split(',')
    for i in range(0, len(p) - 1, 2):
        if p[i] == '2' and dx:
            p[i + 1] = _fmt(float(p[i + 1]) + dx)
        elif p[i] == '3' and dy:
            p[i + 1] = _fmt(float(p[i + 1]) + dy)
    return ','.join(p)


@dataclass
class ObjectFilter:
    """Area (in level units, 1 block = 30) and/or object IDs. Empty fields mean no restriction."""
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    ids: list[int] | None = None

    def is_empty(self) -> bool:
        return all(v is None for v in (self.x_min, self.x_max, self.y_min, self.y_max)) and not self.ids

    def to_agent(self) -> dict | None:
        if self.is_empty():
            return None
        return {'x_min': self.x_min, 'x_max': self.x_max, 'y_min': self.y_min, 'y_max': self.y_max,
                'ids': self.ids or None}
