"""The audio matcher on synthetic mixes: known answers, no media files in the repo."""

import numpy as np
import pytest
from conftest import SR, synth_track

from setlister.audio.features import logmel
from setlister.audio.matcher import MixIndex, align, locate, original_to_online, stretch


def resample(y: np.ndarray, rate: float) -> np.ndarray:
    """Play faster by `rate` (pitch changes too, like a turntable without key lock)."""
    n = int(len(y) / rate)
    return np.interp(np.arange(n) * rate, np.arange(len(y)), y).astype(np.float32)


def mix(parts: list[tuple[np.ndarray, float]], total: float) -> np.ndarray:
    out = np.zeros(int(total * SR), dtype=np.float32)
    for y, start in parts:
        s = int(start * SR)
        fade = int(8 * SR)
        y = y.copy()
        y[:fade] *= np.linspace(0, 1, fade)
        y[-fade:] *= np.linspace(1, 0, fade)
        out[s : s + len(y)] += y[: len(out) - s]
    return out + np.random.default_rng(0).normal(0, 0.02, len(out)).astype(np.float32)


@pytest.fixture(scope="module")
def dj_mix(tracks):
    parts = [(tracks[1], 0.0), (resample(tracks[2], 1.03), 130.0), (tracks[3], 255.0)]
    return mix(parts, 420.0)


def test_locates_tracks_including_tempo_change(tracks, dj_mix):
    index = MixIndex(logmel(dj_mix, SR))
    m1 = locate(index, logmel(tracks[1], SR))
    m2 = locate(index, logmel(tracks[2], SR))
    m3 = locate(index, logmel(tracks[3], SR))
    assert m1 and m1.start < 15
    assert m2 and abs(m2.track_zero - 130) < 3 and abs(m2.rate - 1.03) <= 0.011
    assert m3 and abs(m3.track_zero - 255) < 3
    assert all(m.confidence > 0.4 for m in (m1, m2, m3))


def test_absent_track_is_not_found_confidently(tracks, dj_mix):
    index = MixIndex(logmel(dj_mix, SR))
    m = locate(index, logmel(tracks[4], SR))  # never played; same tempo as track 1
    assert m is None or m.confidence < 0.3


def test_align_trimmed_copy():
    original = synth_track(9, 400, 128)
    online = original[int(37 * SR) : int(360 * SR)]  # trimmed both ends
    segs = align(MixIndex(logmel(original, SR)), logmel(online, SR), step_seconds=40)
    assert segs and abs(segs[0].offset - 37) < 0.5
    assert abs(original_to_online(100.0, segs) - 63.0) < 0.5


def test_stretch_changes_length():
    x = np.random.default_rng(0).random((4, 1000)).astype(np.float32)
    assert stretch(x, 1.25).shape == (4, 800)
