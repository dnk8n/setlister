"""Turn a pile of evidence from many sources into one ordered setlist.

Rules, in plain words:
  * The same track reported by several sources is merged, and its confidence goes up.
  * When two different tracks claim the same stretch, the more confident one wins and the
    other becomes a "contender" for that stretch.
  * Overlapping neighbours (a DJ transition) are split at the middle of the overlap.
  * A gap of more than `min_gap` seconds that nothing explains becomes an "ID" row, listing
    whatever weak guesses fell inside it.
  * DJ software histories are chronological, so placements of history tracks must keep that
    order; `pick_in_order` enforces it.
"""

from __future__ import annotations

from setlister.models import Entry, Evidence, TrackRef
from setlister.textnorm import similarity

SAME_TRACK = 0.8


def same_track(a: TrackRef, b: TrackRef) -> bool:
    if a.isrc and b.isrc:
        return a.isrc == b.isrc
    if a.musicbrainz_recording_id and b.musicbrainz_recording_id:
        return a.musicbrainz_recording_id == b.musicbrainz_recording_id
    return similarity(a.display, b.display) >= SAME_TRACK


def combine(c1: float, c2: float) -> float:
    """Independent-ish evidence: 1 - (1-c1)(1-c2)."""
    return round(1 - (1 - c1) * (1 - c2), 3)


def pick_in_order(options: list[list[Evidence]], min_conf: float = 0.12) -> list[Evidence]:
    """options[i] = candidate placements for the i-th track of a chronological history.
    Choose at most one per track so start times increase, maximising total confidence."""
    flat = [
        (i, e)
        for i, opts in enumerate(options)
        for e in opts
        if e.start is not None and e.confidence >= min_conf
    ]
    flat.sort(key=lambda x: (x[1].start, x[0]))
    n = len(flat)
    best = [e.confidence for _, e in flat]
    prev = [-1] * n
    for j in range(n):
        for k in range(j):
            ordered = flat[k][0] < flat[j][0] and flat[k][1].start < flat[j][1].start
            if ordered and best[k] + flat[j][1].confidence > best[j]:
                best[j] = best[k] + flat[j][1].confidence
                prev[j] = k
    if not n:
        return []
    j = max(range(n), key=lambda x: best[x])
    chosen = []
    while j != -1:
        chosen.append(flat[j][1])
        j = prev[j]
    return chosen[::-1]


def resolve(
    evidence: list[Evidence],
    *,
    duration: float | None,
    min_gap: float = 75.0,
    max_contenders: int = 3,
) -> list[Entry]:
    timed = [e for e in evidence if e.start is not None]
    timed.sort(key=lambda e: e.confidence, reverse=True)
    entries: list[Entry] = []
    weak: list[Evidence] = []

    for e in timed:
        e_end = e.end if e.end is not None else e.start + 60
        merged = False
        for entry in entries:
            entry_end = entry.end if entry.end is not None else entry.start + 60
            near = e.start <= entry_end + 60 and e_end >= entry.start - 60
            if near and same_track(entry.track, e.track):
                entry.start = min(entry.start, e.start)
                if e.end is not None:
                    entry.end = max(entry.end or e.end, e.end)
                entry.confidence = combine(entry.confidence, e.confidence)
                if e.source not in entry.sources:
                    entry.sources.append(e.source)
                _fill(entry.track, e.track)
                merged = True
                break
            overlap = min(entry_end, e_end) - max(entry.start, e.start)
            if overlap > 0.5 * (e_end - e.start):
                weak.append(e)
                merged = True
                break
        if not merged:
            entries.append(
                Entry(
                    start=e.start,
                    end=e.end,
                    track=e.track.model_copy(),
                    confidence=e.confidence,
                    sources=[e.source],
                )
            )

    entries.sort(key=lambda x: x.start)
    _split_transitions(entries)
    entries = _fill_gaps(entries, duration, min_gap)

    for w in weak:
        for entry in entries:
            end = entry.end if entry.end is not None else entry.start + 60
            if entry.start - 30 <= w.start <= end and not same_track(entry.track, w.track):
                if not any(same_track(c, w.track) for c in entry.contenders):
                    entry.contenders.append(w.track)
                break
    for entry in entries:
        entry.contenders = entry.contenders[:max_contenders]
    return entries


def _fill(dst: TrackRef, src: TrackRef) -> None:
    for field in TrackRef.model_fields:
        if getattr(dst, field) in (None, "") and getattr(src, field) not in (None, ""):
            setattr(dst, field, getattr(src, field))


def _split_transitions(entries: list[Entry]) -> None:
    for a, b in zip(entries, entries[1:], strict=False):
        if a.end is None or a.end > b.start:
            if a.end is not None:
                mid = (b.start + a.end) / 2
                a.end, b.start = mid, mid
            else:
                a.end = b.start


def _fill_gaps(entries: list[Entry], duration: float | None, min_gap: float) -> list[Entry]:
    out: list[Entry] = []
    cursor = 0.0
    for e in entries:
        if e.start - cursor > min_gap:
            out.append(Entry(start=cursor, end=e.start, track=TrackRef(), confidence=0.0))
        out.append(e)
        cursor = max(cursor, e.end if e.end is not None else e.start)
    if duration and duration - cursor > min_gap:
        out.append(Entry(start=cursor, end=duration, track=TrackRef(), confidence=0.0))
    if out and out[0].start > 0 and out[0].start < min_gap:
        out[0].start = 0.0  # YouTube chapters must start at 00:00
    return out
