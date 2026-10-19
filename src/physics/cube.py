"""Cube physics (normal size, normal gravity) and click checking.

The constants are the cube's jump in units per second (GD steps physics at 240 Hz): they reproduce a jump about
2.2 blocks high and 0.43 s long. Collisions follow GD's rules closely but not exactly, so treat margins below
~20 ms as risky. Moving objects (move/rotate triggers) are simulated at their editor positions.
"""
import random
from dataclasses import asdict, dataclass, field

from ..levels.timing import UNITS_PER_SECOND
from .world import UNSUPPORTED, World

DT = 1 / 240
JUMP_VELOCITY = 603.72          # click on the ground
ORB_VELOCITY = 603.72           # yellow orb
PAD_VELOCITY = 864.0            # yellow pad
GRAVITY = 2794.1
MAX_FALL = 810.0
HALF = 15.0                     # the cube is 30 x 30
LAND_TOLERANCE = 9.0            # how far below a block's top the cube can still land on it
NEAR = 10.0                     # distance at which an unsupported object stops the simulation


@dataclass
class CubeRun:
    result: str                 # survived | died | stopped
    end_x: float
    cause: str = ''
    obstacle: dict | None = None
    jumps: int = 0
    orbs: int = 0
    pads: int = 0
    wasted_clicks: list[float] = field(default_factory=list)   # x of clicks that did nothing (in the air)

    def as_dict(self) -> dict:
        d = asdict(self)
        d['end_x'] = round(self.end_x, 1)
        d['wasted_clicks'] = [round(x, 1) for x in self.wasted_clicks]
        return d


def simulate(world: World, click_times: list[float], x_start: float, x_end: float, y_start: float = 0.0,
             speed: str = '1x', max_seconds: float = 600.0) -> CubeRun:
    """Runs the cube from (x_start, y_start) to x_end, clicking at the given times (s after the start)."""
    clicks = sorted(click_times)
    ci = 0
    t, x, y, vy = 0.0, x_start, y_start, 0.0
    ground = y_start <= 0
    used: set[int] = set()
    run = CubeRun('survived', x_start)
    while x < x_end and t < max_seconds:
        prev_y = y
        t += DT
        x += UNITS_PER_SECOND[speed] * DT
        pressed = False
        while ci < len(clicks) and clicks[ci] <= t:
            pressed = True
            ci += 1
        x0, x1 = x - HALF, x + HALF
        near = world.near(x0 - 2 * NEAR, x1 + 2 * NEAR)

        for b in near:
            if b.kind in UNSUPPORTED and b.overlaps(x0 - NEAR, y - NEAR, x1 + NEAR, y + 2 * HALF + NEAR):
                return _end(run, 'stopped', x, 'The simulator does not model this object (%s).' % b.kind, b)
            if b.kind.startswith('speed_') and b.overlaps(x0, y, x1, y + 2 * HALF):
                speed = b.kind[len('speed_'):]

        if pressed:
            orb = next((b for b in near if b.kind == 'yellow_orb' and id(b) not in used
                        and b.overlaps(x0, y, x1, y + 2 * HALF)), None)
            if ground:
                vy, ground = JUMP_VELOCITY, False
                run.jumps += 1
            elif orb is not None:
                vy = ORB_VELOCITY
                used.add(id(orb))
                run.orbs += 1
            else:
                run.wasted_clicks.append(x)
        for b in near:
            if b.kind == 'yellow_pad' and id(b) not in used and b.overlaps(x0, y, x1, y + 2 * HALF):
                vy, ground = PAD_VELOCITY, False
                used.add(id(b))
                run.pads += 1

        if not ground:
            vy = max(vy - GRAVITY * DT, -MAX_FALL)
            y += vy * DT
        support = y <= 0
        if y <= 0:
            y = 0.0
        for b in near:
            if b.kind != 'solid' or not (x0 < b.x1 and x1 > b.x0 and y + 2 * HALF > b.y0 and y < b.y1 + 0.01):
                continue
            if vy <= 0 and (prev_y >= b.y1 - 0.5 or y >= b.y1 - LAND_TOLERANCE):
                y = b.y1
                support = True
            elif y < b.y1:
                return _end(run, 'died', x, 'Crashed into the side or bottom of a block.', b)
        if support:
            vy, ground = 0.0, True
        elif ground:
            ground = False
        for b in near:
            if b.kind == 'hazard' and b.overlaps(x0, y, x1, y + 2 * HALF):
                return _end(run, 'died', x, 'Touched a hazard.', b)
    run.end_x = x
    if t >= max_seconds:
        run.result, run.cause = 'stopped', 'Time limit reached.'
    return run


def _end(run: CubeRun, result: str, x: float, cause: str, body) -> CubeRun:
    run.result, run.end_x, run.cause, run.obstacle = result, x, cause, body.describe()
    return run


def check_clicks(world: World, click_times: list[float], x_start: float, x_end: float, y_start: float = 0.0,
                 speed: str = '1x', robustness: bool = True, jitter_ms: float = 40.0, runs: int = 100) -> dict:
    """Simulates the planned clicks and, if they work, how much timing error they tolerate."""
    def run(times):
        return simulate(world, times, x_start, x_end, y_start, speed)

    base = run(click_times)
    report = {'run': base.as_dict(), 'without_clicks': run([]).as_dict()}
    if not robustness or base.result != 'survived':
        return report

    def ok(shift_ms):
        return run([t + shift_ms / 1000 for t in click_times]).result == 'survived'

    lo = hi = 0
    while lo > -150 and ok(lo - 10):
        lo -= 10
    while hi < 150 and ok(hi + 10):
        hi += 10
    rng = random.Random(0)
    failures = sum(run([t + rng.uniform(-jitter_ms, jitter_ms) / 1000 for t in click_times]).result != 'survived'
                   for _ in range(runs))
    report['timing_window_ms'] = [lo, hi]
    report['random_error'] = {'per_click_ms': jitter_ms, 'runs': runs, 'failed': failures}
    return report
