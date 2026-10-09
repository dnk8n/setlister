"""Find where known audio occurs inside a long recording.

Used for two jobs:
  * locating a track (e.g. from the DJ's rekordbox history) inside the set, tolerating the DJ
    having changed its playback speed (with or without key lock);
  * aligning an original recording with the online copy, which may be trimmed or cut.

Method: spectral flux on a 32-band log-mel spectrogram, z-normalised per band, matched with
FFT cross-correlation that is normalised by the local energy of the recording (NCC). A coarse
search over playback rates finds candidates, then each candidate is verified by checking many
short windows of the track at the positions the candidate predicts, against a background of
random positions. Plain numpy/scipy; no GPU needed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
from scipy import fft as sfft

from setlister.audio.features import N_MELS, Features

TIMBRE = slice(N_MELS, 2 * N_MELS)  # rows of the matching feature holding spectral shape
# A window "hits" when its spectral shape matches the recording at the predicted spot well in
# absolute terms and clearly better than elsewhere in the set. Calibrated on a real 2 h set:
# true placements reach NCC 0.7-0.98, false ones never exceeded 0.56.
MIN_NCC = 0.6
MIN_LIFT = 0.35
DEBUG = bool(os.environ.get("SETLISTER_DEBUG_MATCH"))


def _znorm(x: np.ndarray) -> np.ndarray:
    x = x - x.mean(axis=1, keepdims=True)
    return x / (x.std(axis=1, keepdims=True) + 1e-6)


def _flux(logmel: np.ndarray) -> np.ndarray:
    """Matching feature: onsets per band (rhythm) stacked with locally detrended
    spectral shape (timbre/notes). Rhythm alone matches any track at a similar tempo;
    the timbre half is what makes a match specific to one track."""
    onsets = np.maximum(np.diff(logmel, axis=1), 0.0)
    shape = logmel[:, 1:]
    k = 64  # ~3 s moving average at 11 025 Hz / 512 hop
    kernel = np.ones(k, dtype=np.float32) / k
    trend = np.stack([np.convolve(b, kernel, mode="same") for b in shape])
    detrended = shape - trend
    return np.concatenate([_znorm(onsets), _znorm(detrended)]).astype(np.float32)


def stretch(logmel: np.ndarray, rate: float) -> np.ndarray:
    """Resample the time axis as if the audio were played `rate` times faster."""
    n = logmel.shape[1]
    m = max(2, int(round(n / rate)))
    x = np.linspace(0, n - 1, m)
    idx = np.arange(n)
    return np.stack([np.interp(x, idx, band) for band in logmel]).astype(np.float32)


@dataclass
class MixIndex:
    """Pre-computed FFTs of a recording, so many templates can be matched quickly."""

    features: Features
    flux: np.ndarray = field(init=False)
    nfft: int = field(init=False)
    spectra: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.flux = _flux(self.features.logmel)
        n = self.flux.shape[1]
        self.nfft = sfft.next_fast_len(2 * n)
        self.spectra = sfft.rfft(self.flux, n=self.nfft, axis=1)
        self._energy_cumsum = np.concatenate([[0.0], np.cumsum((self.flux**2).sum(axis=0))])

    @property
    def fps(self) -> float:
        return self.features.fps

    @property
    def frames(self) -> int:
        return self.flux.shape[1]

    def correlate(self, template: np.ndarray) -> np.ndarray:
        """NCC of a (bands, m) flux template at every lag. Values roughly in [-1, 1]."""
        m = template.shape[1]
        if m >= self.frames:
            return np.zeros(1, dtype=np.float32)
        t = template - template.mean(axis=1, keepdims=True)
        tnorm = np.sqrt((t**2).sum()) + 1e-6
        tspec = sfft.rfft(t, n=self.nfft, axis=1)
        raw = sfft.irfft((self.spectra * np.conj(tspec)).sum(axis=0), n=self.nfft)
        valid = self.frames - m + 1
        local = self._energy_cumsum[m : m + valid] - self._energy_cumsum[:valid]
        return (raw[:valid] / (tnorm * np.sqrt(local + 1e-6))).astype(np.float32)

    def _cumsum(self, rows: slice | None) -> np.ndarray:
        if rows is None:
            return self._energy_cumsum
        key = (rows.start, rows.stop)
        cache = self.__dict__.setdefault("_row_cumsums", {})
        if key not in cache:
            cache[key] = np.concatenate([[0.0], np.cumsum((self.flux[rows] ** 2).sum(axis=0))])
        return cache[key]

    def score_range(
        self, template: np.ndarray, lo: int, hi: int, rows: slice | None = None
    ) -> np.ndarray:
        """NCC of a template at every lag in [lo, hi] (NaN where out of range).
        `rows` restricts the comparison to some feature rows (the template has only those)."""
        m = template.shape[1]
        flux = self.flux if rows is None else self.flux[rows]
        cumsum = self._cumsum(rows)
        out = np.full(hi - lo + 1, np.nan, dtype=np.float32)
        a, b = max(lo, 0), min(hi, self.frames - m)
        if a > b:
            return out
        t = template - template.mean(axis=1, keepdims=True)
        tnorm = np.sqrt((t**2).sum()) + 1e-6
        view = np.lib.stride_tricks.sliding_window_view(flux[:, a : b + m], m, axis=1)
        dots = np.einsum("bkm,bm->k", view, t)
        energy = cumsum[a + m : b + m + 1] - cumsum[a : b + 1]
        out[a - lo : b - lo + 1] = dots / (tnorm * np.sqrt(energy + 1e-6))
        return out

    def score_at(self, template: np.ndarray, lags: np.ndarray) -> np.ndarray:
        """NCC of a template at specific lags (direct dot products; cheap for few lags)."""
        m = template.shape[1]
        t = template - template.mean(axis=1, keepdims=True)
        tnorm = np.sqrt((t**2).sum()) + 1e-6
        out = np.full(len(lags), np.nan, dtype=np.float32)
        for i, lag in enumerate(lags):
            if lag >= 0 and lag + m <= self.frames:
                seg = self.flux[:, lag : lag + m]
                out[i] = (seg * t).sum() / (tnorm * np.sqrt((seg**2).sum()) + 1e-6)
        return out


def beat_period(flux: np.ndarray, fps: float) -> float:
    """Beat period in (fractional) frames, 60-180 BPM, from the autocorrelation of onsets.

    Refined over 16 beats, because an error of a fraction of a frame per beat adds up to
    whole beats when shifting by several bars."""
    onset = flux[: flux.shape[0] // 2].sum(axis=0)
    onset = onset - onset.mean()
    ac = np.correlate(onset, onset, mode="full")[len(onset) - 1 :]
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 60)
    if hi >= len(ac):
        return fps / 2
    period = lo + int(np.argmax(ac[lo:hi]))
    centre = 16 * period
    if centre + 16 < len(ac):
        window = ac[centre - 16 : centre + 17]
        return (centre - 16 + int(np.argmax(window))) / 16
    return float(period)


@dataclass
class Match:
    start: float  # recording time where the track's audio is first clearly audible (s)
    end: float  # recording time where it was last clearly audible (s)
    track_zero: float  # recording time that corresponds to t=0 of the track file (s)
    rate: float  # playback rate (1.0 = original speed)
    confidence: float  # 0..1
    windows_matched: int
    windows_total: int


def _peaks(corr: np.ndarray, k: int, min_dist: int) -> list[int]:
    order = np.argsort(corr)[::-1]
    chosen: list[int] = []
    for i in order:
        if all(abs(int(i) - c) >= min_dist for c in chosen):
            chosen.append(int(i))
            if len(chosen) == k:
                break
    return chosen


def locate(index: MixIndex, track: Features, **kwargs) -> Match | None:
    """Best placement of a track inside the recording, or None."""
    found = locate_candidates(index, track, **kwargs)
    return found[0] if found else None


def locate_candidates(
    index: MixIndex,
    track: Features,
    *,
    max_rate_change: float = 0.08,
    rate_step: float = 0.005,
    excerpt_seconds: float = 48.0,
    window_seconds: float = 12.0,
    hop_seconds: float = 6.0,
    candidates_per_rate: int = 2,
) -> list[Match]:
    """Plausible placements of a track inside the recording, best first.

    Several are returned because a repetitive, loop-based track can be weakly matched at a few
    places; the resolver picks between them using other evidence (e.g. play order)."""
    fps = index.fps
    rates = np.arange(1 - max_rate_change, 1 + max_rate_change + 1e-9, rate_step)
    half = int(excerpt_seconds * fps / 2)

    # 1. coarse search: middle excerpt of the track at every candidate playback rate
    cands: list[tuple[float, float, int]] = []  # (score, rate, lag of track frame 0)
    for r in rates:
        flux = _flux(stretch(track.logmel, r))
        mid = flux.shape[1] // 2
        if flux.shape[1] < 2 * half + 2:
            ex, ex_start = flux, 0
        else:
            ex, ex_start = flux[:, mid - half : mid + half], mid - half
        corr = index.correlate(ex)
        for p in _peaks(corr, candidates_per_rate, int(30 * fps)):
            cands.append((float(corr[p]), float(r), p - ex_start))
    cands.sort(reverse=True)

    # 2. verify the best few (distinct) candidates window by window
    win, hop = int(window_seconds * fps), int(hop_seconds * fps)
    tol = int(1.5 * fps)
    fine = 3
    found: list[Match] = []
    seen: list[int] = []
    for _, r, zero in cands:
        if any(abs(zero - s) < 20 * fps for s in seen):
            continue
        seen.append(zero)
        if len(seen) > 6:
            break
        flux = _flux(stretch(track.logmel, r))
        beat = beat_period(flux, fps)
        k = np.concatenate([np.arange(1, 4), 4 * np.arange(1, 9)])  # 1-3 beats, 1-8 bars
        shifts = np.concatenate([k, -k]) * beat
        shifts = np.unique(np.round(shifts).astype(int))
        starts = np.arange(0, max(1, flux.shape[1] - win), hop)
        # pass 1: best lag per window within a wide tolerance, to measure tempo drift
        rough = []
        for s in starts:
            tmpl = flux[:, s : s + win]
            if tmpl.shape[1] < win:
                continue
            sc = index.score_range(tmpl, zero + s - tol, zero + s + tol)
            if not np.all(np.isnan(sc)):
                rough.append((s, int(np.nanargmax(sc)) - tol, float(np.nanmax(sc))))
        if len(rough) < 3:
            continue
        rs = np.array(rough)
        good = rs[rs[:, 2] >= np.median(rs[:, 2])]
        slope, intercept = np.polyfit(good[:, 0], good[:, 1], 1) if len(good) >= 2 else (0.0, 0.0)
        # pass 2: score each window on the fitted path vs. the same window shifted by whole
        # beats/bars, both with the same small tolerance (a fair comparison)
        zs, times = [], []
        # random places elsewhere in the set (not inside this candidate placement)
        pool = np.random.default_rng(0).integers(0, max(1, index.frames - win - 8), 200)
        pool = pool[(pool < zero - win) | (pool > zero + flux.shape[1])]
        rand_lags = pool[:24] if len(pool) >= 8 else pool
        for s, _, _ in rough:
            s = int(s)
            tmpl = flux[:, s : s + win]
            lag = int(round(zero + s + intercept + slope * s))
            near = index.score_range(tmpl, lag - fine, lag + fine)
            if np.all(np.isnan(near)):
                continue  # predicted position falls outside the recording
            local = np.nanmax(near)
            bg = []
            for sh in shifts:
                b = lag + sh if 0 <= lag + sh <= index.frames - win else lag - sh
                v = index.score_range(tmpl, b - fine, b + fine)
                if not np.all(np.isnan(v)):
                    bg.append(np.nanmax(v))
            if len(bg) < 6:
                continue
            bg_a = np.array(bg)
            spread = np.median(np.abs(bg_a - np.median(bg_a))) * 1.4826 + 0.02
            z_align = (local - np.median(bg_a)) / spread
            # Timbre-only check against random places in the set: catches loop-based tracks,
            # where shifting by whole bars looks just as good, so z_align is weak.
            tt = tmpl[TIMBRE]
            loc_t = np.nanmax(index.score_range(tt, lag - fine, lag + fine, rows=TIMBRE))
            rnd = [
                np.nanmax(index.score_range(tt, int(r), int(r) + 2 * fine, rows=TIMBRE))
                for r in rand_lags
            ]
            rnd_a = np.array([v for v in rnd if not np.isnan(v)])
            z_timbre = (loc_t - np.median(rnd_a)) / (
                np.median(np.abs(rnd_a - np.median(rnd_a))) * 1.4826 + 0.02
            )
            if DEBUG:
                print(
                    f"    w{s / fps:5.0f}s z_align={z_align:5.1f} z_timbre={z_timbre:5.1f} "
                    f"ncc={loc_t:.2f} elsewhere={np.median(rnd_a):.2f}"
                )
            hit = (loc_t >= MIN_NCC and loc_t - np.median(rnd_a) >= MIN_LIFT) or z_timbre > 8
            zs.append((hit, float(loc_t)))
            times.append(lag / fps)
        if not zs:
            continue
        hit = np.array([h for h, _ in zs])
        ncc = np.array([v for _, v in zs])
        times_a = np.array(times)
        if hit.sum() < 3:
            continue
        first, last = int(np.argmax(hit)), int(len(hit) - 1 - np.argmax(hit[::-1]))
        density = hit[first : last + 1].mean()
        strength = float(np.median(ncc[hit]))
        span = times_a[last] - times_a[first] + window_seconds
        conf = float(
            density
            * np.clip((strength - 0.45) / 0.35, 0.2, 1.0)
            * min(1.0, hit.sum() / 6)
            * min(1.0, span / 90.0)  # a real play lasts minutes, not seconds
        )
        m = Match(
            start=float(times_a[first]),
            end=float(times_a[last] + window_seconds),
            track_zero=zero / fps,
            rate=r,
            confidence=round(conf, 3),
            windows_matched=int(hit.sum()),
            windows_total=len(hit),
        )
        if m.confidence > 0.05:
            found.append(m)
    found.sort(key=lambda m: m.confidence, reverse=True)
    return found


@dataclass
class AlignmentSegment:
    online_start: float  # seconds in the online copy
    online_end: float
    offset: float  # original_time = online_time * rate + offset
    rate: float = 1.0  # >1 means the online copy plays faster than the original


def _align_points(
    original: MixIndex,
    flux: np.ndarray,
    fps: float,
    win: int,
    step: int,
    min_ncc: float,
    min_margin: float,
) -> tuple[list[tuple[float, float]], int]:
    points, tried = [], 0
    for s in range(0, max(1, flux.shape[1] - win), step):
        tried += 1
        corr = original.correlate(flux[:, s : s + win])
        p = int(np.argmax(corr))
        away = np.ones(len(corr), bool)
        away[max(0, p - int(2 * fps)) : p + int(2 * fps)] = False
        second = corr[away].max() if away.any() else 0.0
        if corr[p] >= min_ncc and corr[p] - second >= min_margin:
            points.append((s / fps, (p - s) / fps))
    return points, tried


def _probe_rate(original: MixIndex, online: Features, win: int) -> float:
    """Best playback rate of the online copy relative to the original, from a few windows.
    Re-uploads are sometimes sped up or slowed down (e.g. 24/25 fps video conversion = 4 %)."""
    best_rate, best_score = 1.0, -1.0
    for r in np.arange(0.95, 1.0501, 0.0025):
        flux = _flux(stretch(online.logmel, 1 / r))
        m = flux.shape[1]
        scores = [
            float(original.correlate(flux[:, int(m * q) : int(m * q) + win]).max())
            for q in (0.25, 0.5, 0.75)
            if int(m * q) + win < m
        ]
        if scores and np.mean(scores) > best_score:
            best_rate, best_score = float(r), float(np.mean(scores))
    return best_rate


def align(
    original: MixIndex,
    online: Features,
    *,
    window_seconds: float = 30.0,
    step_seconds: float = 60.0,
    min_ncc: float = 0.5,
    min_margin: float = 0.08,
) -> list[AlignmentSegment]:
    """Map the online copy onto the original recording. Handles trims, cuts and a copy that
    was uploaded at a slightly different speed."""
    fps = online.fps
    win, step = int(window_seconds * fps), int(step_seconds * fps)
    rate = 1.0
    points, tried = _align_points(
        original, _flux(online.logmel), fps, win, step, min_ncc, min_margin
    )
    if len(points) < 0.3 * tried:
        probed = _probe_rate(original, online, win)
        if abs(probed - 1.0) > 1e-6:
            flux = _flux(stretch(online.logmel, 1 / probed))
            p2, t2 = _align_points(original, flux, fps, win, step, min_ncc, min_margin)
            if len(p2) > len(points):
                rate = probed
                # p2 holds (time at original speed, offset); online time = that / rate
                points = [(t / rate, off) for t, off in p2]
    segments: list[AlignmentSegment] = []
    for t, off in points:
        # off = original_time - stretched_time, and stretched_time = online_time * rate
        if segments and abs(segments[-1].offset - off) < 1.0:
            segments[-1].online_end = t + window_seconds / rate
        else:
            segments.append(AlignmentSegment(t, t + window_seconds / rate, off, rate))
    return segments


def original_to_online(
    t: float, segments: list[AlignmentSegment], slack: float = 60.0
) -> float | None:
    """Convert a time in the original recording into the online copy's timeline."""
    for seg in segments:
        o = (t - seg.offset) / seg.rate
        if seg.online_start - slack <= o <= seg.online_end + slack:
            return o
    return None
