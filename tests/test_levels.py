import tempfile
import unittest
from pathlib import Path

from gd_editor_mcp.levels import (Level, ObjectFilter, compress_level_string, decompress_level_string, join_objects,
                                  read_gmd, shift_object, split_objects, write_gmd)

HEADER = 'kS38,1_40_2_125_3_255_11_255_12_255_13_255_4_-1_6_1000_7_1_15_1_18_0_8_1|,kA13,24.25,kA6,10,kA7,18'


class ObjectsTest(unittest.TestCase):
    def test_split_accepts_semicolons_and_newlines(self):
        self.assertEqual(split_objects('1,1,2,15,3,15;\n1,8,2,45,3,15;;'), ['1,1,2,15,3,15', '1,8,2,45,3,15'])

    def test_join_adds_trailing_separator(self):
        self.assertEqual(join_objects(['a', 'b']), 'a;b;')
        self.assertEqual(join_objects([]), '')

    def test_shift_only_touches_position_keys(self):
        self.assertEqual(shift_object('1,2,2,15,3,15,21,2', 30, -7.5), '1,2,2,45,3,7.5,21,2')

    def test_filter_empty_and_serialization(self):
        self.assertTrue(ObjectFilter().is_empty())
        self.assertIsNone(ObjectFilter().to_agent())
        self.assertEqual(ObjectFilter(x_min=0, ids=[8]).to_agent()['ids'], [8])


class GmdTest(unittest.TestCase):
    def test_compress_roundtrip_and_plain_passthrough(self):
        s = HEADER + ';1,1,2,15,3,15;'
        self.assertTrue(compress_level_string(s).startswith('H4sI'))
        self.assertEqual(decompress_level_string(compress_level_string(s)), s)
        self.assertEqual(decompress_level_string(s), s)

    def test_level_string_requires_header(self):
        with self.assertRaises(ValueError):
            Level.from_level_string('1,1,2,15,3,15;')

    def test_write_then_read_gmd(self):
        level = Level(HEADER, ['1,1,2,15,3,15', '1,8,2,45,3,15'], name='Test & <level>', description='unicode: ñ é',
                      song_id=739991)
        with tempfile.TemporaryDirectory() as d:
            path = write_gmd(Path(d) / 'x.gmd', level)
            text = path.read_text(encoding='utf-8')
            self.assertTrue(text.startswith('<?xml version="1.0"?><plist version="1.0" gjver="2.0"><dict><k>kCEK</k>'))
            back = read_gmd(path)
        self.assertEqual(back.header, HEADER)
        self.assertEqual(back.objects, level.objects)
        self.assertEqual(back.song_id, 739991)
        self.assertEqual(back.description, 'unicode: ñ é')

    def test_example_level_is_readable(self):
        path = Path(__file__).resolve().parent / 'data' / 'PixelSphere.gmd'
        level = read_gmd(path)
        self.assertEqual(level.song_id, 739991)
        self.assertGreater(len(level.objects), 4000)
        self.assertIn('kA13,24.25', level.header)


if __name__ == '__main__':
    unittest.main()
