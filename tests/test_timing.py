import unittest

from gd_editor_mcp.levels import Timeline
from gd_editor_mcp.levels.timing import UNITS_PER_SECOND


class TimelineTest(unittest.TestCase):
    def test_constant_speed_and_song_offset(self):
        t = Timeline('1x', song_offset=24.25)
        row = t.song_time_to_x(25.25)
        self.assertAlmostEqual(row['x'], UNITS_PER_SECOND['1x'], places=1)
        self.assertEqual(row['speed'], '1x')
        self.assertTrue(t.song_time_to_x(20.0)['before_start'])

    def test_speed_portal_changes_speed_where_it_is_touched(self):
        header = 'kS38,x,kA4,0,kA13,10'
        portal_center = 1000.0
        t = Timeline.from_level(header, ['1,202,2,%s,3,45' % portal_center])
        touch = portal_center - 15 - 51 / 2
        self.assertEqual([s.speed for s in t.segments], ['1x', '2x'])
        self.assertAlmostEqual(t.segments[1].x, touch)
        reach = touch / UNITS_PER_SECOND['1x']
        x_after = t.song_time_to_x(10 + reach + 1.0)['x']
        self.assertAlmostEqual(x_after, touch + UNITS_PER_SECOND['2x'], places=1)

    def test_start_speed_from_header_and_roundtrip(self):
        t = Timeline.from_level('kS38,x,kA4,2,kA13,0', ['1,201,2,3000,3,45', '1,1,2,15,3,15'])
        self.assertEqual(t.segments[0].speed, '2x')
        for song_time in (0.5, 3.0, 9.0, 20.0):
            x = t.song_time_to_x(song_time)['x']
            self.assertAlmostEqual(t.x_to_song_time(x), song_time, places=3)

    def test_portals_with_the_current_speed_are_ignored(self):
        t = Timeline.from_level('kS38,x', ['1,201,2,500,3,45'])
        self.assertEqual(len(t.segments), 1)


if __name__ == '__main__':
    unittest.main()
