import unittest

from gd_editor_mcp.physics import check_layout


def blocks(*cells: tuple[int, int]) -> list[str]:
    """Blocks at grid cells (column, row): cell (0, 0) is the first one on the ground."""
    return ['1,1,2,%d,3,%d' % (15 + 30 * c, 15 + 30 * r) for c, r in cells]


def spikes(*cells: tuple[int, int]) -> list[str]:
    return ['1,8,2,%d,3,%d' % (15 + 30 * c, 15 + 30 * r) for c, r in cells]


def rules(report: dict) -> list[str]:
    return sorted(p['rule'] for p in report['problems'])


class LayoutTest(unittest.TestCase):
    def test_spikes_flush_in_a_one_block_pit(self):
        objs = blocks((0, 0), (1, 0), (2, 0), (5, 0), (6, 0)) + spikes((3, 0), (4, 0))
        report = check_layout(objs)
        self.assertFalse(report['ok'])
        self.assertEqual(rules(report), ['flush_pit'])
        self.assertIn('flush_pit', report['fixes'])

    def test_a_two_block_pit_is_fine(self):
        walls = [(c, r) for c in (0, 1, 2, 5, 6) for r in (0, 1)]
        report = check_layout(blocks(*walls) + spikes((3, 0), (4, 0)))
        self.assertTrue(report['ok'], report['problems'])

    def test_a_spike_next_to_a_single_block_is_fine(self):
        self.assertTrue(check_layout(blocks((0, 0)) + spikes((1, 0)))['ok'])

    def test_spikes_on_blocks_and_hanging_from_a_ceiling_are_fine(self):
        objs = blocks((0, 0), (1, 0), (0, 4)) + spikes((0, 1), (1, 1)) + ['1,8,2,15,3,105,6,180']
        self.assertTrue(check_layout(objs)['ok'])

    def test_spike_inside_a_block(self):
        report = check_layout(['1,1,2,100,3,15', '1,8,2,115,3,15'])
        self.assertEqual(rules(report), ['spike_in_block'])
        self.assertEqual(report['problems'][0]['severity'], 'error')

    def test_thin_gaps_overlaps_and_duplicates(self):
        self.assertEqual(rules(check_layout(['1,1,2,15,3,15', '1,1,2,50,3,15'])), ['thin_gap'])
        self.assertEqual(rules(check_layout(['1,1,2,15,3,15', '1,1,2,35,3,15'])), ['overlap'])
        self.assertEqual(rules(check_layout(['1,1,2,15,3,15', '1,1,2,15,3,15'])), ['duplicate'])
        self.assertEqual(rules(check_layout(['1,1,2,15,3,15', '1,1,2,15,3,50'])), ['thin_gap'])

    def test_spikes_and_the_ground(self):
        self.assertEqual(rules(check_layout(['1,8,2,15,3,5'])), ['sunk_spike'])
        self.assertEqual(rules(check_layout(['1,8,2,15,3,22'])), ['thin_gap'])

    def test_slopes_meet_blocks_cleanly(self):
        steep = ['1,289,2,15,3,15', '1,1,2,45,3,15', '1,289,2,45,3,45', '1,1,2,75,3,15', '1,1,2,75,3,45']
        gentle = ['1,1,2,135,3,15', '1,1,2,165,3,15', '1,291,2,150,3,45', '1,1,2,195,3,15', '1,1,2,195,3,45']
        report = check_layout(steep + gentle)
        self.assertTrue(report['ok'], report['problems'])
        self.assertEqual(report['off_grid']['count'], 0)
        self.assertEqual(rules(check_layout(['1,291,2,120,3,15', '1,1,2,105,3,15'])), ['overlap'])

    def test_off_grid_is_counted_but_not_a_problem(self):
        report = check_layout(['1,1,2,20,3,15'])
        self.assertTrue(report['ok'])
        self.assertEqual(report['off_grid']['count'], 1)

    def test_hidden_no_touch_and_decoration_objects_are_ignored(self):
        objs = ['1,1,2,100,3,15', '1,8,2,115,3,15,121,1', '1,8,2,115,3,15,135,1', '1,211,2,110,3,15']
        report = check_layout(objs)
        self.assertTrue(report['ok'])
        self.assertEqual(report['checked_objects'], 1)

    def test_area_filter_and_limit(self):
        objs = []
        for k in range(10):
            objs += ['1,1,2,%d,3,15' % (300 * k + 15), '1,8,2,%d,3,15' % (300 * k + 30)]
        self.assertEqual(len(check_layout(objs)['problems']), 10)
        self.assertEqual(len(check_layout(objs, x_min=600, x_max=1250)['problems']), 3)
        limited = check_layout(objs, max_problems=4)
        self.assertEqual((len(limited['problems']), limited['truncated'], limited['counts']['spike_in_block']),
                         (4, True, 10))


if __name__ == '__main__':
    unittest.main()
