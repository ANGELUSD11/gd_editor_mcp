"""Layout checks: how the level looks, not how it plays.

Finds the mistakes that make a layout look sloppy or broken: spikes partly inside blocks, spikes flush in a
1-block pit (they look embedded between blocks), thin gaps and overlaps between blocks, duplicated objects, spikes
sunk into the ground, and blocks or spikes off the 30-unit grid. Only blocks, slopes and full-size spikes are
checked; decoration and objects marked "no touch" (121) or hidden (135) are left alone.
"""
from dataclasses import dataclass

from .world import _object_dict, body_from_object, hitbox_table

TOUCH = 0.5            # closer than this counts as touching
THIN = 15.0            # gaps narrower than half a block look like mistakes
OVERLAP = 2.0          # overlaps deeper than this are visible
BAND = 5.0             # two objects share a row (or column) if they overlap this much across it
BUCKET = 60.0
FULL_SPIKE = (6.0, 12.0)     # hitbox of the full-size spikes (8, 144, 177, 216): their sprite fills a 30x30 cell

SEVERITY = {'spike_in_block': 'error', 'flush_pit': 'warning', 'thin_gap': 'warning', 'overlap': 'warning',
            'duplicate': 'warning', 'sunk_spike': 'warning'}
FIXES = {
    'spike_in_block': 'Move the spike out of the block: spikes sit on top of blocks or next to them, never inside.',
    'flush_pit': 'The spike tips are level with the floor on both sides, so they look embedded between blocks. '
                 'Make the pit at least 2 blocks deep (raise the platforms), use half spikes, or leave it empty.',
    'thin_gap': 'Make the objects touch or leave a full block between them; keep blocks and spikes on the '
                '30-unit grid (centers at 15 + 30k).',
    'overlap': 'The blocks overlap each other: line them up on the 30-unit grid so their edges meet.',
    'duplicate': 'Delete the extra copy: identical objects on top of each other are an invisible mistake.',
    'sunk_spike': 'Raise the spike so its base sits on the ground (y=15 for the first row).',
}


@dataclass
class Shape:
    oid: int
    kind: str              # solid | slope | spike
    x: float
    y: float
    x0: float              # visual box
    y0: float
    x1: float
    y1: float
    rot: float = 0.0
    upright: bool = False  # spikes: pointing up

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    def describe(self) -> dict:
        return {'id': self.oid, 'x': round(self.x, 2), 'y': round(self.y, 2)}


def shape_from_object(obj: str) -> Shape | None:
    """Visual box of a block, slope or full-size spike; None for anything else."""
    d = _object_dict(obj)
    try:
        oid = int(float(d.get('1', 0)))
        x, y = float(d.get('2', 0)), float(d.get('3', 0))
        rot = float(d.get('6', 0) or 0) % 360
    except ValueError:
        return None
    entry = hitbox_table().get(oid)
    if entry is None or d.get('121') == '1' or d.get('135') == '1':
        return None
    if entry['kind'] in ('solid', 'slope'):
        b = body_from_object(obj)
        return Shape(oid, entry['kind'], x, y, b.x0, b.y0, b.x1, b.y1, rot) if b else None
    if entry['kind'] == 'hazard' and entry['shape'] == 'box' and (entry['w'], entry['h']) == FULL_SPIKE:
        if rot % 90:
            return None                                  # tilted: no reliable box
        uniform = float(d.get('32', 1) or 1)
        w = 30 * abs(float(d.get('128', uniform) or uniform))
        h = 30 * abs(float(d.get('129', uniform) or uniform))
        if rot in (90, 270):
            w, h = h, w
        upright = rot in (0, 180) and (rot == 0) != (d.get('5') == '1')
        return Shape(oid, 'spike', x, y, x - w / 2, y - h / 2, x + w / 2, y + h / 2, rot, upright)
    return None


def _on_grid(v: float, tolerance: float = TOUCH) -> bool:
    """v is a multiple of 30 (one block)."""
    return abs((v + 15) % 30 - 15) <= tolerance


def _gap(a0: float, a1: float, b0: float, b1: float) -> float:
    """Distance between two intervals (negative: how much they overlap)."""
    return max(a0, b0) - min(a1, b1)


class _Index:
    def __init__(self, shapes: list[Shape]):
        self.buckets: dict[int, list[Shape]] = {}
        for s in shapes:
            for k in range(int(s.x0 // BUCKET), int(s.x1 // BUCKET) + 1):
                self.buckets.setdefault(k, []).append(s)

    def near(self, x0: float, x1: float) -> list[Shape]:
        seen, out = set(), []
        for k in range(int((x0 - THIN) // BUCKET), int((x1 + THIN) // BUCKET) + 1):
            for s in self.buckets.get(k, ()):
                if id(s) not in seen:
                    seen.add(id(s))
                    out.append(s)
        return out


def _flush_wall(index: _Index, run: list[Shape], side: int) -> Shape | None:
    """A 1-high block right next to a run of spikes whose top is level with the spike tips."""
    edge = run[0].x0 if side < 0 else run[-1].x1
    top, bottom = run[0].y1, run[0].y0
    for s in index.near(edge, edge):
        if s.kind != 'solid':
            continue
        gap = edge - s.x1 if side < 0 else s.x0 - edge
        if not -OVERLAP <= gap < THIN or abs(s.y1 - top) > OVERLAP or s.y0 > bottom + OVERLAP:
            continue
        covered = any(o.kind in ('solid', 'slope') and abs(o.y0 - s.y1) <= OVERLAP and
                      _gap(o.x0, o.x1, s.x0, s.x1) < -BAND for o in index.near(s.x0, s.x1))
        if not covered:
            return s
    return None


def check_layout(objects: list[str], max_problems: int = 40, x_min: float | None = None,
                 x_max: float | None = None) -> dict:
    """Checks the objects and reports the problems found between x_min and x_max (all of them by default)."""
    shapes = [s for s in map(shape_from_object, objects) if s is not None]
    found: list[dict] = []

    def report(rule: str, at: Shape, detail: str, *others: Shape) -> None:
        if (x_min is not None and at.x < x_min) or (x_max is not None and at.x > x_max):
            return
        found.append({'rule': rule, 'severity': SEVERITY[rule], 'x': round(at.x, 2), 'y': round(at.y, 2),
                      'detail': detail, 'objects': [s.describe() for s in (at, *others)]})

    # duplicates: the same object twice in the same place
    unique, seen = [], set()
    for s in shapes:
        key = (s.oid, round(s.x, 1), round(s.y, 1), s.rot)
        if key in seen:
            report('duplicate', s, 'Object %d appears twice at the same position.' % s.oid)
        else:
            seen.add(key)
            unique.append(s)
    shapes = unique

    # pairs that touch or nearly touch
    order = sorted(shapes, key=lambda s: s.x0)
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            if b.x0 > a.x1 + THIN:
                break
            gx, gy = _gap(a.x0, a.x1, b.x0, b.x1), _gap(a.y0, a.y1, b.y0, b.y1)
            kinds = {a.kind, b.kind}
            if gx < -OVERLAP and gy < -OVERLAP:
                if kinds == {'spike', 'solid'}:
                    spike, block = (a, b) if a.kind == 'spike' else (b, a)
                    report('spike_in_block', spike, 'The spike is %.0f units inside a block.'
                           % min(-gx, -gy), block)
                elif 'spike' not in kinds:
                    report('overlap', a, 'Two blocks overlap by %.0f x %.0f units.' % (-gx, -gy), b)
            elif gy < -BAND and TOUCH < gx < THIN:
                report('thin_gap', a, 'A %.1f-unit gap between objects in the same row.' % gx, b)
            elif gx < -BAND and TOUCH < gy < THIN:
                lower, upper = (a, b) if a.y0 < b.y0 else (b, a)
                if (upper.kind == 'spike' and not upper.upright) or (lower.kind == 'spike' and lower.upright):
                    continue                   # a gap at a spike's tip is design, not a placement mistake
                report('thin_gap', upper, 'A %.1f-unit gap between objects stacked vertically.' % gy, lower)

    # spikes and the ground
    index = _Index(shapes)
    for s in shapes:
        if s.kind == 'spike' and s.upright and s.y0 < -OVERLAP < s.y1:
            report('sunk_spike', s, 'The spike is %.0f units below the ground.' % -s.y0)
        elif TOUCH < s.y0 < THIN and (s.kind == 'solid' or (s.kind == 'spike' and s.upright)):
            if not any(o is not s and o.y1 <= s.y0 + TOUCH and _gap(o.x0, o.x1, s.x0, s.x1) < -BAND
                       for o in index.near(s.x0, s.x1)):
                report('thin_gap', s, 'Floating %.1f units above the ground.' % s.y0)

    # runs of spikes flush between two 1-high walls
    spikes = sorted((s for s in shapes if s.kind == 'spike' and s.upright), key=lambda s: (round(s.y0), s.x0))
    runs: list[list[Shape]] = []
    for s in spikes:
        last = runs[-1][-1] if runs else None
        if last and abs(last.y0 - s.y0) < 1 and abs(last.y1 - s.y1) < 1 and s.x0 - last.x1 < THIN:
            runs[-1].append(s)
        else:
            runs.append([s])
    for run in runs:
        left, right = _flush_wall(index, run, -1), _flush_wall(index, run, 1)
        if left and right:
            report('flush_pit', run[0], '%d spike(s) between two 1-high walls, tips level with the floor.'
                   % len(run), *run[1:], left, right)

    # off the grid (reported as a count: fine for decoration, sloppy for gameplay blocks and spikes)
    off = [s for s in shapes
           if _on_grid(s.w, 0.01) and _on_grid(s.h, 0.01) and not (_on_grid(s.x0) and _on_grid(s.y0))
           and (x_min is None or s.x >= x_min) and (x_max is None or s.x <= x_max)]

    found.sort(key=lambda p: (p['severity'] != 'error', p['x']))
    counts: dict[str, int] = {}
    for p in found:
        counts[p['rule']] = counts.get(p['rule'], 0) + 1
    return {
        'checked_objects': len(shapes),
        'ok': not found,
        'counts': counts,
        'problems': found[:max_problems],
        'truncated': len(found) > max_problems,
        'fixes': {rule: FIXES[rule] for rule in counts},
        'off_grid': {'count': len(off), 'examples': [s.describe() for s in off[:5]],
                     'note': 'Blocks and spikes whose edges are not on the 30-unit grid. Fine for decoration; '
                             'for gameplay it leaves thin gaps and edges that do not line up.'},
    }
