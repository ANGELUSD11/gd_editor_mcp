import base64
import gzip
import tempfile
import unittest
from pathlib import Path

import numpy as np

from gd_editor_mcp.music import analyze_audio, get_song, list_songs
from gd_editor_mcp.music.analysis import SR
from gd_editor_mcp.music.library import decode_save


def synth_song(bpm: float, first: float, seconds: float = 40.0, quiet_bars: int = 8) -> np.ndarray:
    """Kick on every beat and a hi-hat on every off-beat; quiet for `quiet_bars` bars, then loud (a drop)."""
    rng = np.random.default_rng(0)
    x = np.zeros(int(seconds * SR), dtype=np.float32)
    period = 60 / bpm
    beat = 0
    while first + beat * period < seconds - 0.3:
        amp = 0.25 if beat // 4 < quiet_bars else 1.0
        s = int((first + beat * period) * SR)
        k = np.arange(int(0.12 * SR)) / SR
        x[s:s + len(k)] += amp * np.sin(2 * np.pi * 55 * k) * np.exp(-k * 30)
        h = int((first + (beat + 0.5) * period) * SR)
        m = int(0.03 * SR)
        x[h:h + m] += amp * 0.3 * rng.standard_normal(m) * np.exp(-np.arange(m) / SR * 150)
        beat += 1
    return x + 0.01 * rng.standard_normal(len(x)).astype(np.float32)


class AnalysisTest(unittest.TestCase):
    def check(self, bpm, first):
        a = analyze_audio(synth_song(bpm, first))
        self.assertAlmostEqual(a.bpm, bpm, delta=0.1)
        phase_error = ((a.first_beat - first + a.beat_period / 2) % a.beat_period) - a.beat_period / 2
        self.assertLess(abs(phase_error), 0.015)
        self.assertAlmostEqual(a.first_downbeat, first, delta=0.015)
        drop = first + 32 * 60 / bpm
        self.assertTrue(any(abs(d - drop) < 0.05 for d in a.drops), (a.drops, drop))
        self.assertGreater(a.grid_fit, 1.5)

    def test_tempo_phase_bars_and_drop(self):
        for bpm, first in ((128, 0.5), (100, 0.27), (174, 0.1), (190, 0.4)):
            with self.subTest(bpm=bpm):
                self.check(bpm, first)

    def test_too_short_audio_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze_audio(np.zeros(SR, dtype=np.float32))


def encode_save(xml: str) -> bytes:
    data = base64.urlsafe_b64encode(gzip.compress(xml.encode()))
    return bytes(b ^ 11 for b in data)


class LibraryTest(unittest.TestCase):
    def test_decode_save_and_song_metadata(self):
        xml = ('<?xml version="1.0"?><plist><dict>'
               '<d><k>kCEK</k><i>6</i><k>1</k><i>739991</i><k>2</k><s>Creo - Sphere</s><k>4</k><s>CreoMusic</s></d>'
               '<d><k>kCEK</k><i>6</i><k>1</k><i>123</i><k>2</k><s>A &amp; B</s><k>4</k><s>Someone</s></d>'
               '</dict></plist>')
        self.assertEqual(decode_save(encode_save(xml)), xml)
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / 'CCGameManager.dat').write_bytes(encode_save(xml))
            (folder / '739991.mp3').write_bytes(b'x')
            (folder / '10000126.ogg').write_bytes(b'x')
            (folder / 'notes.txt').write_text('x')
            songs = list_songs(folder=folder)
            self.assertEqual([s.song_id for s in songs], [739991, 10000126])
            self.assertEqual(songs[0].name, 'Creo - Sphere')
            self.assertEqual([s.song_id for s in list_songs('creo', folder=folder)], [739991])
            missing = get_song(123, folder)
            self.assertEqual(missing.name, 'A & B')
            self.assertFalse(missing.downloaded)


if __name__ == '__main__':
    unittest.main()
