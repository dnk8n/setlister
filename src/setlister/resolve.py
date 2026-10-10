"""Turn a pile of evidence from many sources into one ordered setlist.

Rules, in plain words:
  * The same track reported by several sources is merged, and its confidence goes up.
  * When two different tracks claim the same stretch, the more confident one wins and the
    other becomes a "contender" for that stretch.
  * Overlapping neighbours (a DJ transition) are split at the middle of the overlap.
  * Two independent systems agreeing on a track is strong evidence: two of Shazam, AcoustID
    and a local file match, or a recogniser naming a track the DJ's history says was played.
    Such rows get at least `CONSENSUS` confidence and no short-play penalty.
  * A detection inside a track's stretch whose title is that track's title by another
    artist is the sample source, not a separate track: it becomes a footnote.
  * Detections spanning a minute or less are heavily penalised (DJs rarely play a track that
    briefly), and named rows that end up below `min_confidence` are left out of the list.
  * A gap of more than `min_gap` seconds that nothing explains becomes an "ID" row, listing
    whatever weak guesses fell inside it.
  * DJ software histories are chronological, so placements of history tracks must keep that
    order; `pick_in_order` enforces it.
"""

from __future__ import annotations

import re

from setlister.models import Entry, Evidence, Sample, Source, TrackRef
from setlister.textnorm import norm, similarity

SAME_TRACK = 0.8
MIN_ROW_SECONDS = 20.0
SHORT_PLAY = 60.0  # seconds; a detection this short is heavily penalised
SHORT_PLAY_FULL = 120.0  # no penalty from here on
SHORT_PLAY_FACTOR = 0.3
AUDIO_SOURCES = {Source.SHAZAM, Source.ACOUSTID, Source.LOCAL_MATCH}
CONSENSUS = 0.9


def same_track(a: TrackRef, b: TrackRef) -> bool:
    """Same recording? IDs decide when they agree; otherwise compare names leniently, since
    sources credit artists differently ('Pepe Bradock' vs 'Pépé Bradock & The Grand Brûlé's
    Choir'). Different ISRCs don't prove different tracks (re-releases get new ones)."""
    if a.isrc and a.isrc == b.isrc:
        return True
    if a.musicbrainz_recording_id and a.musicbrainz_recording_id == b.musicbrainz_recording_id:
        return True
    if similarity(a.display, b.display) >= SAME_TRACK:
        return True
    if not (a.title and b.title) or similarity(a.title, b.title) < 0.85:
        return False
    ta, tb = set(norm(a.artist).split()), set(norm(b.artist).split())
    return bool(ta & tb) or not ta or not tb


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
    min_confidence: float = 0.5,
    rejected: list[Entry] | None = None,
    clip: bool = False,
    played: list[TrackRef] | None = None,
) -> list[Entry]:
    """Evidence -> setlist rows. Named rows below `min_confidence` (after the short-play
    penalty) are left out of the list and appended to `rejected`, if given.

    `clip` is for highlight reels: every piece is seconds long by design, so there is no
    short-play penalty and rows only a few seconds long are kept. `played` is the DJ's history
    (untimed): a recogniser naming one of those tracks counts as agreement."""
    min_row = 3.0 if clip else MIN_ROW_SECONDS
    if clip:
        min_gap = min(min_gap, 10.0)
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

    _attach_samples(entries, weak)
    for entry in entries:
        agreed = consensus(entry, played)
        factor = 1.0 if clip or agreed else short_play_factor(entry, duration)
        entry.confidence = round(entry.confidence * factor, 3)
        if agreed:
            entry.confidence = max(entry.confidence, CONSENSUS)
    dropped = [e for e in entries if e.confidence < min_confidence]
    entries = [e for e in entries if e.confidence >= min_confidence]
    if rejected is not None:
        rejected.extend(sorted(dropped, key=lambda x: x.start))

    entries.sort(key=lambda x: x.start)
    _split_transitions(entries)
    entries = _fill_gaps(entries, duration, min_gap)
    entries = _drop_slivers(entries, min_row)

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


def consensus(entry: Entry, played: list[TrackRef] | None = None) -> bool:
    """Did two independent systems name this track: two audio systems, or one plus the DJ's
    own history?"""
    heard = AUDIO_SOURCES.intersection(entry.sources)
    if len(heard) >= 2:
        return True
    return bool(heard) and any(same_track(entry.track, t) for t in played or [])


def _base_title(title: str) -> str:
    """'Never Grow Old (Re-plant)' -> 'never grow old'."""
    return norm(re.sub(r"[\(\[].*?[\)\]]", " ", title))


def is_sample_of(source: TrackRef, track: TrackRef) -> bool:
    """Same title, different artist: Aretha Franklin's 'Never Grow Old' inside Floorplan's
    'Never Grow Old (Re-plant)'."""
    a, b = _base_title(source.title), _base_title(track.title)
    if not a or a != b:
        return False
    sa, sb = set(norm(source.artist).split()), set(norm(track.artist).split())
    return bool(sa) and not (sa & sb)


def _attach_samples(entries: list[Entry], weak: list[Evidence]) -> None:
    """Weaker detections near a track that are its sample source become footnotes."""
    for e in sorted(entries, key=lambda x: x.confidence, reverse=True):
        if e not in entries:
            continue
        lo, hi = e.start - 30, (e.end if e.end is not None else e.start + 60) + 30
        for other in [x for x in entries if x is not e and x.confidence <= e.confidence]:
            if lo <= other.start <= hi and is_sample_of(other.track, e.track):
                add_sample(e, other.track)
                entries.remove(other)
        for w in list(weak):
            if w.start is not None and lo <= w.start <= hi and is_sample_of(w.track, e.track):
                add_sample(e, w.track)
                weak.remove(w)


def add_sample(entry: Entry, track: TrackRef, source: str = "heard in the mix") -> None:
    """Add a footnote once; a MusicBrainz relation outranks a recogniser's guess."""
    for s in entry.samples:
        if same_track(s.track, track):
            if source == "MusicBrainz":
                s.source = source
            return
    entry.samples.append(Sample(track=track.model_copy(), source=source))


def short_play_factor(entry: Entry, duration: float | None) -> float:
    """DJs rarely play a track for a minute or less, so a detection that short is probably a
    mismatch: x0.3 at <= 60 s, rising linearly to x1 at 2 min. Rows touching the start or end
    of the recording are exempt, because the recording may have cut the play short."""
    end = entry.end if entry.end is not None else entry.start + 60
    at_edge = entry.start <= 5 or (duration is not None and end >= duration - 5)
    span = end - entry.start
    if at_edge or span >= SHORT_PLAY_FULL:
        return 1.0
    if span <= SHORT_PLAY:
        return SHORT_PLAY_FACTOR
    return SHORT_PLAY_FACTOR + (1 - SHORT_PLAY_FACTOR) * (span - SHORT_PLAY) / (
        SHORT_PLAY_FULL - SHORT_PLAY
    )


def _drop_slivers(entries: list[Entry], min_len: float = MIN_ROW_SECONDS) -> list[Entry]:
    """Rows shorter than `min_len` (YouTube chapters need >= 10 s, and a play that short is
    noise) are folded into a neighbour; a named sliver becomes that neighbour's contender."""
    out: list[Entry] = []
    for e in entries:
        length = (e.end if e.end is not None else e.start + min_len) - e.start
        if length >= min_len or not out and len(entries) == 1:
            out.append(e)
            continue
        target = out[-1] if out else None
        if target is None:
            continue  # handled below: the next row will start at 0
        target.end = e.end if e.end is not None else target.end
        if not e.is_unknown and not same_track(target.track, e.track):
            target.contenders.append(e.track)
    if out and entries and out[0].start > entries[0].start:
        first = entries[0]
        if not first.is_unknown and not same_track(out[0].track, first.track):
            out[0].contenders.insert(0, first.track)
        out[0].start = entries[0].start
    return out


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
