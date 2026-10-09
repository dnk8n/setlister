import numpy as np
import pytest
from scipy.signal import lfilter

SR = 11025


def synth_track(seed: int, seconds: float, bpm: float, sr: int = SR) -> np.ndarray:
    """A deterministic fake 'track' with its own sound palette, like real tracks have: a
    seeded kick, filtered hats, a note pattern with seeded harmonics, a sustained pad, human-ish
    velocities, and an arrangement (with breakdowns) that changes every few bars."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    y = np.zeros(n, dtype=np.float32)
    beat = 60.0 / bpm
    # palette
    tk = np.arange(int(0.15 * sr)) / sr
    f0, decay = rng.uniform(40, 70), rng.uniform(12, 30)
    kick = np.sin(2 * np.pi * (f0 + 90 * np.exp(-tk * 30)) * tk) * np.exp(-tk * decay)
    hat_len = int(rng.uniform(0.02, 0.06) * sr)
    a = rng.uniform(-0.9, 0.5)
    hat = lfilter([1, -1], [1, a], rng.normal(0, 1, hat_len)) * np.exp(
        -np.arange(hat_len) / (0.01 * sr)
    )
    harmonics = rng.uniform(0, 1, int(rng.integers(1, 6)))
    root = 55 * 2 ** (rng.integers(0, 12) / 12)
    notes = root * 2 ** (rng.choice([0, 2, 3, 5, 7, 10, 12, 14, 15, 17, 19, 24], size=64) / 12)
    section_beats = int(rng.choice([16, 32, 64]))
    pattern = rng.random((64, section_beats * 4)) < 0.3
    level = 0.5 + rng.random(64)
    no_kick = rng.random(64) < 0.2  # breakdowns
    pad_chords = root * 2 ** (rng.integers(0, 12, size=(64, 3)) / 12)

    def tone(freq: float, dur: int) -> np.ndarray:
        tt = np.arange(dur) / sr
        w = sum(h * np.sin(2 * np.pi * freq * (i + 1) * tt) for i, h in enumerate(harmonics))
        return w * np.exp(-tt * 8)

    i, t = 0, 0.0
    while t < seconds - 1:
        s = int(t * sr)
        section = (i // section_beats) % 64
        if i % section_beats == 0:  # pad for the whole section
            dur = min(n - s, int(section_beats * beat * sr))
            tt = np.arange(dur) / sr
            pad = sum(np.sin(2 * np.pi * f * 2 * tt) for f in pad_chords[section]) * 0.05
            y[s : s + dur] += pad * (0.5 + 0.5 * np.sin(2 * np.pi * tt / 7))
        if not no_kick[section]:
            y[s : s + len(kick)] += rng.uniform(0.6, 1.0) * kick[: max(0, n - s)]
        for k in range(4):  # 16th-note steps
            ss = int((t + k * beat / 4) * sr)
            if pattern[section, (i % section_beats) * 4 + k]:
                dur = int(beat / 4 * sr)
                note = tone(notes[(section + k) % 64], dur) * 0.4 * level[section]
                y[ss : ss + dur] += note[: max(0, n - ss)]
            if k == 2:
                y[ss : ss + hat_len] += rng.uniform(0.05, 0.3) * hat[: max(0, n - ss)]
        t += beat
        i += 1
    return y / (np.abs(y).max() + 1e-9)


@pytest.fixture(scope="session")
def tracks():
    return {k: synth_track(k, 150, bpm) for k, bpm in [(1, 124), (2, 126), (3, 125), (4, 124)]}
