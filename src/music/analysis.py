"""Tempo, beat grid and structure of a song, computed from its audio signal.

This is signal analysis, not listening: it assumes a steady tempo (true for most Geometry Dash music) and finds
the beat grid that best fits the song's onsets, the bar phase, energy-based sections, drops and short cuts.
"""
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

SR = 22050
WIN = 1024
HOP = 256
FPS = SR / HOP
FRAME_CENTER = WIN / 2 / SR      # time of a frame = index / FPS + FRAME_CENTER


@dataclass
class Section:
    start: float          # song time (s)
    end: float
    start_bar: int
    bars: int
    energy: float         # mean loudness, 0-1 relative to the loudest part of the song
    kind: str             # intro | build | drop | break | steady | outro


@dataclass
class SongAnalysis:
    duration: float
    bpm: float
    beat_period: float
    first_beat: float     # song time of the first beat of the grid (beat n is at first_beat + n * beat_period)
    first_downbeat: float  # song time of the first bar start (estimate)
    beats_per_bar: int
    bars: int
    grid_fit: float       # how much stronger onsets are on the grid than off it (>1.5 is a clear beat)
    alternatives: list[dict] = field(default_factory=list)   # half/double tempo candidates
    sections: list[Section] = field(default_factory=list)
    drops: list[float] = field(default_factory=list)          # song times where a loud section starts
    cuts: list[dict] = field(default_factory=list)            # short near-silences (start, duration)

    def beat_time(self, beat: float) -> float:
        return self.first_beat + beat * self.beat_period

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ('duration', 'beat_period', 'first_beat', 'first_downbeat', 'grid_fit'):
            d[k] = round(d[k], 4)
        d['bpm'] = round(self.bpm, 2)
        d['drops'] = [round(t, 3) for t in self.drops]
        for s in d['sections']:
            s['start'], s['end'], s['energy'] = round(s['start'], 3), round(s['end'], 3), round(s['energy'], 2)
        return d


# ---------------------------------------------------------------- audio and features
def load_audio(path: str | Path, sr: int = SR) -> np.ndarray:
    import miniaudio
    decoded = miniaudio.decode_file(str(path), output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1,
                                    sample_rate=sr)
    return np.frombuffer(decoded.samples, dtype=np.float32).copy()


def _features(x: np.ndarray):
    """Per frame: spectral flux, low-band (kick/bass) energy and RMS loudness."""
    frames = np.lib.stride_tricks.sliding_window_view(x, WIN)[::HOP]
    window = np.hanning(WIN).astype(np.float32)
    n = len(frames)
    flux = np.zeros(n, np.float32)
    low = np.zeros(n, np.float32)
    rms = np.zeros(n, np.float32)
    prev = None
    for a in range(0, n, 2048):
        f = frames[a:a + 2048]
        spec = np.abs(np.fft.rfft(f * window, axis=1)).astype(np.float32)
        logspec = np.log1p(100.0 * spec)
        stacked = logspec if prev is None else np.vstack([prev, logspec])
        diff = np.diff(stacked, axis=0, prepend=stacked[:1]) if prev is None else np.diff(stacked, axis=0)
        flux[a:a + len(f)] = np.maximum(diff, 0).sum(1)
        low[a:a + len(f)] = spec[:, 1:8].sum(1)          # ~20-150 Hz
        rms[a:a + len(f)] = np.sqrt((f ** 2).mean(1))
        prev = logspec[-1:]
    # Linear (not log) on purpose: in a log scale the faint low end of hi-hats looks as strong as a kick.
    lowflux = np.maximum(np.diff(low, prepend=low[:1]), 0)
    return flux, lowflux, rms


def _onset_strength(e: np.ndarray) -> np.ndarray:
    k = int(FPS * 0.5) | 1
    e = np.maximum(e - np.convolve(e, np.ones(k) / k, mode='same'), 0)
    return e / (e.std() or 1.0)


# ---------------------------------------------------------------- tempo and beat grid
def _autocorr(e: np.ndarray) -> np.ndarray:
    n = len(e)
    f = np.fft.rfft(e - e.mean(), 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    return ac / (ac[0] or 1.0)


def _comb(ac: np.ndarray, bpm: float) -> float:
    lag = 60.0 / bpm * FPS
    score = 0.0
    for k, w in ((1, 1.0), (2, 0.5), (3, 0.33), (4, 0.25)):
        pos = lag * k
        i = int(pos)
        if i + 1 >= len(ac):
            break
        score += w * ((i + 1 - pos) * ac[i] + (pos - i) * ac[i + 1])
    return score


def _grid(env: np.ndarray, period: float, step: float = 0.25):
    """Best phase (in frames) of a beat grid with this period and the mean onset strength on it."""
    n_beats = int((len(env) - 1) / period) - 1
    phases = np.arange(0, period, step)
    idx = np.rint(phases[:, None] + np.arange(n_beats)[None, :] * period).astype(int)
    sums = env[idx].mean(1)
    best = int(np.argmax(sums))
    return phases[best], float(sums[best])


def _tempo(env: np.ndarray):
    ac = _autocorr(env)
    bpms = np.arange(60.0, 220.0, 0.25)
    raw = np.array([max(_comb(ac, b), 0.0) for b in bpms])
    prior = np.exp(-0.5 * (np.log2(bpms / 130.0) / 0.9) ** 2)    # GD music is mostly 100-180 BPM
    coarse = float(bpms[int(np.argmax(raw * prior))])
    fine = np.arange(coarse * 0.985, coarse * 1.015, 0.01)
    scores = [_grid(env, 60.0 / b * FPS, 0.5)[1] for b in fine]
    bpm = float(fine[int(np.argmax(scores))])
    alternatives = []
    for factor in (0.5, 2.0):
        alt = bpm * factor
        if 50 <= alt <= 260:
            rel = _comb(ac, alt) / (_comb(ac, bpm) or 1.0)
            alternatives.append({'bpm': round(alt, 2), 'relative_strength': round(float(rel), 2)})
    return bpm, alternatives


def _beat_grid(env: np.ndarray, low_onsets: np.ndarray, bpm: float):
    """Phase (frames) of the beat grid and the mean onset strength on the beats and half-way between them."""
    period_f = 60.0 / bpm * FPS

    def strength(e, phase):
        return float(e[np.rint(np.arange(phase, len(e) - 1, period_f)).astype(int)].mean())

    phase_f, _ = _grid(env, period_f)
    # Hi-hats on the off-beats can pull the grid half a beat late: the beat is where the low end hits harder.
    if strength(low_onsets, phase_f + period_f / 2) > 1.1 * strength(low_onsets, phase_f):
        phase_f = (phase_f + period_f / 2) % period_f
    return phase_f, strength(env, phase_f), strength(env, phase_f + period_f / 2)


# ---------------------------------------------------------------- structure
def _bar_phase(rms_beats: np.ndarray, low_beats: np.ndarray, per_bar: int) -> int:
    """Which beat (0..per_bar-1) starts the bars: where loudness changes and kicks hit hardest."""
    change = np.abs(np.diff(rms_beats, prepend=rms_beats[:1]))
    change[:per_bar] = 0                                    # the start and the end of the file are not bar lines
    change[-per_bar:] = 0
    scores = [change[j::per_bar].sum() / (change.sum() or 1) + 0.5 * low_beats[j::per_bar].mean() / (low_beats.mean() or 1)
              for j in range(per_bar)]
    return int(np.argmax(scores))


def _sections(bar_energy: np.ndarray, bar_times: np.ndarray, duration: float) -> list[Section]:
    level = np.digitize(bar_energy, [0.45, 0.75])          # 0 low, 1 mid, 2 high
    runs = []
    start = 0
    for i in range(1, len(level) + 1):
        if i == len(level) or level[i] != level[start]:
            runs.append([start, i, int(level[start])])
            start = i
    merged = []
    for r in runs:                                          # absorb one-bar blips into the previous section
        if merged and r[1] - r[0] < 2:
            merged[-1][1] = r[1]
        elif merged and merged[-1][2] == r[2]:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    out = []
    for k, (a, b, lv) in enumerate(merged):
        prev_lv = merged[k - 1][2] if k else None
        next_lv = merged[k + 1][2] if k + 1 < len(merged) else None
        if k == 0 and lv < 2:
            kind = 'intro'
        elif next_lv is None and lv < 2 and prev_lv is not None and prev_lv > lv:
            kind = 'outro'
        elif lv == 2 and (prev_lv is None or prev_lv < 2):
            kind = 'drop'
        elif lv < 2 and prev_lv == 2:
            kind = 'break'
        elif lv < 2 and next_lv == 2:
            kind = 'build'
        else:
            kind = 'steady'
        end = bar_times[b] if b < len(bar_times) else duration
        out.append(Section(float(bar_times[a]), float(end), a, b - a, float(bar_energy[a:b].mean()), kind))
    return out


def _cuts(rms: np.ndarray, period: float, first: float, duration: float) -> list[dict]:
    """Short near-silences inside the music (stops before drops, stutters)."""
    k = int(FPS * period * 8) | 1
    local = np.convolve(rms, np.ones(k) / k, mode='same')
    quiet = (rms < 0.2 * local) & (local > 0.1 * rms.max())
    out = []
    i = 0
    min_len = max(2, int(FPS * period / 4))
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if j - i >= min_len:
                t = i / FPS + FRAME_CENTER
                out.append({'start': round(t, 3), 'duration': round((j - i) / FPS, 3),
                            'beat': round((t - first) / period, 2)})
            i = j
        else:
            i += 1
    return out[:40]


# ---------------------------------------------------------------- entry points
def analyze_audio(x: np.ndarray, sr: int = SR, beats_per_bar: int = 4) -> SongAnalysis:
    if sr != SR:
        raise ValueError('analyze_audio expects %d Hz audio' % SR)
    if len(x) < SR * 4:
        raise ValueError('The audio is too short to analyze (less than 4 s).')
    duration = len(x) / SR
    flux, lowflux, rms = _features(x.astype(np.float32))
    low_onsets = _onset_strength(lowflux)
    full_onsets = _onset_strength(flux)
    env = full_onsets + 2.0 * low_onsets                    # kicks and bass mark the beat in GD music
    # Tempo from the low end mostly: off-beat hi-hats make every half-beat multiple look periodic.
    bpm, alternatives = _tempo(low_onsets + 0.5 * full_onsets)
    phase_f, on_grid, off_grid = _beat_grid(env, low_onsets, bpm)
    if on_grid < 1.25 * off_grid and bpm * 2 <= 230:
        # Half-way between the beats is as strong as the beats: the real tempo is double.
        alternatives = [{'bpm': round(bpm, 2), 'relative_strength': 1.0}]
        bpm *= 2
        phase_f, on_grid, off_grid = _beat_grid(env, low_onsets, bpm)
    period_f = 60.0 / bpm * FPS
    period = 60.0 / bpm
    first_beat = phase_f / FPS + FRAME_CENTER

    beat_idx = np.rint(np.arange(phase_f, len(env) - 1, period_f)).astype(int)
    span = max(1, int(period_f))
    rms_beats = np.array([rms[i:i + span].mean() for i in beat_idx])
    low_beats = np.array([lowflux[i:i + max(1, span // 4)].mean() for i in beat_idx])
    bar_phase = _bar_phase(rms_beats, low_beats, beats_per_bar)
    first_downbeat = first_beat + bar_phase * period

    bar_starts = np.arange(first_downbeat, duration, period * beats_per_bar)
    bar_energy = np.array([rms[int((t - FRAME_CENTER) * FPS):int((t - FRAME_CENTER + period * beats_per_bar) * FPS)].mean()
                           for t in bar_starts])
    bar_energy = bar_energy / (np.percentile(bar_energy, 95) or 1.0)
    sections = _sections(np.clip(bar_energy, 0, 1.2), bar_starts, duration)
    return SongAnalysis(
        duration=duration, bpm=bpm, beat_period=period, first_beat=first_beat, first_downbeat=first_downbeat,
        beats_per_bar=beats_per_bar, bars=len(bar_starts), grid_fit=on_grid / (off_grid or 1e-9),
        alternatives=alternatives, sections=sections,
        drops=[s.start for s in sections if s.kind == 'drop'], cuts=_cuts(rms, period, first_beat, duration))


def analyze_file(path: str | Path, beats_per_bar: int = 4) -> SongAnalysis:
    return analyze_audio(load_audio(path), SR, beats_per_bar)
