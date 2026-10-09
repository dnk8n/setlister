# Architecture

All times in the output are relative to the **online** copy of the set.

```
            ┌───────────── text (description, chapters, comments) ───┐
URL ──────► │                                                         │
            │  history (.txt/.m3u8) ─► local files ─► tags            │──► evidence ─► resolve ─► enrich ─► out/
original ─► │        └─► audio match (tempo-tolerant) ─┐               │
            │  original ⇄ online alignment (trims) ────┴─► times      │
            └───────────── recognisers on unexplained stretches ─────┘
```

## Evidence

Every source emits `Evidence(track, source, confidence, start, end, order)`. The resolver:

1. merges the same track from different sources (confidence combines as 1-(1-a)(1-b));
2. keeps the more confident of two different tracks claiming the same stretch, recording the
   other as a contender;
3. splits overlapping neighbours in the middle of the overlap (the DJ transition);
4. turns an unexplained gap longer than 75 s into an `ID` row, suggesting history tracks that
   sit between its neighbours in play order;
5. enforces chronological order for placements that came from a DJ history
   (`resolve.pick_in_order`, a small dynamic programme).

## The audio matcher (`audio/matcher.py`)

Features: a 32-band log-mel spectrogram at 11 025 Hz (≈21.5 frames/s), turned into two halves:
per-band onsets (rhythm) and locally detrended spectral shape (timbre and notes).

1. **Coarse search.** The middle 48 s of a track, resampled for each playback rate in
   ±8 % (0.5 % steps), is cross-correlated with the whole recording via FFT, normalised by
   the recording's local energy.
2. **Verification.** For the best candidates, 12 s windows every 6 s are scored along the
   predicted path (with a fitted drift correction). A window counts when its spectral shape
   matches well in absolute terms (NCC ≥ 0.6) *and* clearly better than random places elsewhere
   in the set. Thresholds were calibrated on a real two-hour b2b set, where true placements
   scored 0.7–0.98 and false ones never exceeded 0.56.
3. **Confidence** combines how densely windows hit inside the span, how strongly, how many,
   and how long the span is.

Why not off-the-shelf fingerprinting for this step? Landmark fingerprinters (audfprint,
Chromaprint) assume original speed; Panako handles tempo changes but is AGPL Java. Matching
known files is a simpler problem than open-set recognition, so a few dozen lines of
numpy/scipy on librosa features do it well and stay MIT.

## Hardware

The default path is light enough for any laptop CPU. GPU / Apple Neural Engine models (e.g.
beat-synchronous structure analysis to find transitions without any reference) are on the
roadmap as an optional extra; they should only run where cheaper evidence left gaps.
