import unittest
from pathlib import Path

from gd_editor_mcp.levels import Timeline, read_gmd
from gd_editor_mcp.levels.timing import UNITS_PER_SECOND
from gd_editor_mcp.physics import World, check_clicks, simulate

V1 = UNITS_PER_SECOND['1x']
APEX_1X = 67.3          # a ground jump peaks 67 units after the click at 1x


def world(*objects: str) -> World:
    return World.from_objects(list(objects))


class CubeTest(unittest.TestCase):
    def test_spike_kills_without_a_jump_and_is_cleared_with_one(self):
        w = world('1,8,2,150,3,15')
        dead = simulate(w, [], 0, 400)
        self.assertEqual((dead.result, dead.obstacle['kind']), ('died', 'hazard'))
        click = (150 - APEX_1X) / V1
        report = check_clicks(w, [click], 0, 400)
        self.assertEqual(report['run']['result'], 'survived')
        lo, hi = report['timing_window_ms']
        self.assertLess(lo, -50)
        self.assertGreater(hi, 50)

    def test_wall_crash_and_platform_landing(self):
        wall = world('1,1,2,300,3,15', '1,1,2,300,3,45', '1,1,2,300,3,75')
        self.assertEqual(simulate(wall, [(300 - 120) / V1], 0, 500).cause, 'Crashed into the side or bottom of a block.')
        step = world('1,1,2,200,3,15', '1,1,2,230,3,15', '1,1,2,260,3,15')
        run = simulate(step, [(200 - 75) / V1], 0, 250)
        self.assertEqual(run.result, 'survived')

    def test_yellow_pad_launches_over_spikes(self):
        w = world('1,35,2,100,3,2', *('1,8,2,%d,3,15' % x for x in (140, 170, 200)))
        run = simulate(w, [], 0, 500)
        self.assertEqual((run.result, run.pads), ('survived', 1))

    def test_yellow_orb_extends_a_jump(self):
        spikes = ['1,8,2,%d,3,15' % x for x in range(110, 270, 30)]
        w = world('1,36,2,150,3,70', *spikes)
        self.assertEqual(simulate(w, [60 / V1], 0, 500).result, 'died')
        run = simulate(w, [60 / V1, 150 / V1], 0, 500)
        self.assertEqual((run.result, run.orbs), ('survived', 1))

    def test_speed_portal_changes_speed(self):
        objs = ['1,202,2,300,3,45', '1,8,2,900,3,15']
        w = world(*objs)
        timeline = Timeline.from_level('kA4,0', objs)
        click_x = 900 - 83.7                   # apex distance at 2x
        good = timeline.time_at(click_x) - timeline.time_at(0)
        self.assertEqual(simulate(w, [good], 0, 1100).result, 'survived')
        self.assertEqual(simulate(w, [click_x / V1], 0, 1100).result, 'died')   # timed as if it were still 1x

    def test_unsupported_objects_stop_the_simulation(self):
        run = simulate(world('1,13,2,300,3,45'), [], 0, 600)
        self.assertEqual((run.result, run.obstacle['kind']), ('stopped', 'portal'))

    def test_rotated_and_no_touch_objects(self):
        self.assertEqual(simulate(world('1,8,2,150,3,75,6,180'), [], 0, 400).result, 'survived')
        self.assertEqual(simulate(world('1,8,2,150,3,15,121,1'), [], 0, 400).result, 'survived')


class PixelSphereRegressionTest(unittest.TestCase):
    """The cube sections of the sample level pass with the clicks they were designed for."""

    def test_cube_sections(self):
        level = read_gmd(Path(__file__).resolve().parent / 'data' / 'PixelSphere.gmd')
        w = World.from_objects(level.objects)
        tl = Timeline.from_level(level.header, level.objects)

        def xb(beat):
            return tl.song_time_to_x(tl.song_offset + 0.6 * beat)['x']

        sections = (([4, 6, 8, 10, 12, 14, 18, 22, 24, 24.5, 26, 28, 29, 30], 0.0, xb(32) - 10, 0.0, '1x'),
                    ([66, 68, 72, 72.5, 74, 75, 76, 78], xb(64) + 46, xb(80) - 60, 90.0, '2x'))
        for beats, x0, x1, y0, speed in sections:
            with self.subTest(start=x0):
                times = [tl.time_at(xb(b)) - tl.time_at(x0) for b in beats]
                report = check_clicks(w, times, x0, x1, y0, speed, runs=30)
                self.assertEqual(report['run']['result'], 'survived')
                self.assertEqual(report['without_clicks']['result'], 'died')
                lo, hi = report['timing_window_ms']
                self.assertLessEqual(lo, -50)
                self.assertGreaterEqual(hi, 50)
                self.assertEqual(report['random_error']['failed'], 0)


if __name__ == '__main__':
    unittest.main()
