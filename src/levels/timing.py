"""Song time <-> level x position, from the level's start speed, song offset and speed portals.

The player starts at x = 0 when the song is at `song_offset` seconds and moves at the speed of the last speed
portal it touched. A portal is touched before its center: when the player's hitbox (30 units wide) reaches the
portal's hitbox.
"""
from dataclasses import dataclass

UNITS_PER_SECOND = {'0.5x': 251.16, '1x': 311.58, '2x': 387.42, '3x': 468.0, '4x': 576.0}
START_SPEED = {0: '1x', 1: '0.5x', 2: '2x', 3: '3x', 4: '4x'}        # header key kA4
SPEED_PORTALS = {200: ('0.5x', 35.0), 201: ('1x', 33.0), 202: ('2x', 51.0), 203: ('3x', 65.0), 1334: ('4x', 69.0)}
PLAYER_HALF_WIDTH = 15.0


def header_values(header: str) -> dict[str, str]:
    parts = header.split(',')
    return {parts[i]: parts[i + 1] for i in range(0, len(parts) - 1, 2)}


@dataclass
class Segment:
    x: float          # where this speed starts
    time: float       # level time (s) when the player reaches x
    speed: str


class Timeline:
    def __init__(self, start_speed: str = '1x', song_offset: float = 0.0,
                 portals: list[tuple[float, str]] | None = None):
        """portals: (activation x, speed) pairs."""
        self.song_offset = song_offset
        self.segments = [Segment(0.0, 0.0, start_speed)]
        for x, speed in sorted(p for p in (portals or []) if p[0] > 0):
            last = self.segments[-1]
            if speed == last.speed:
                continue
            t = last.time + (x - last.x) / UNITS_PER_SECOND[last.speed]
            self.segments.append(Segment(x, t, speed))

    @classmethod
    def from_level(cls, header: str, objects: list[str]) -> 'Timeline':
        kv = header_values(header)
        start = START_SPEED.get(int(float(kv.get('kA4', '0') or 0)), '1x')
        offset = float(kv.get('kA13', '0') or 0)
        portals = []
        for obj in objects:
            p = obj.split(',')
            d = {p[i]: p[i + 1] for i in range(0, len(p) - 1, 2)}
            oid = int(float(d.get('1', 0)))
            if oid in SPEED_PORTALS:
                speed, width = SPEED_PORTALS[oid]
                portals.append((float(d.get('2', 0)) - PLAYER_HALF_WIDTH - width / 2, speed))
        return cls(start, offset, portals)

    def x_at(self, level_time: float) -> tuple[float, str]:
        seg = self.segments[0]
        for s in self.segments:
            if s.time <= level_time:
                seg = s
        return seg.x + (level_time - seg.time) * UNITS_PER_SECOND[seg.speed], seg.speed

    def time_at(self, x: float) -> float:
        seg = self.segments[0]
        for s in self.segments:
            if s.x <= x:
                seg = s
        return seg.time + (x - seg.x) / UNITS_PER_SECOND[seg.speed]

    def song_time_to_x(self, song_time: float) -> dict:
        level_time = song_time - self.song_offset
        x, speed = self.x_at(level_time)
        return {'song_time': round(song_time, 4), 'level_time': round(level_time, 4), 'x': round(x, 2),
                'speed': speed, 'before_start': level_time < 0}

    def x_to_song_time(self, x: float) -> float:
        return self.time_at(x) + self.song_offset
