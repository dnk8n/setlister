"""Read DJ play histories exported from rekordbox (and anything else writing M3U/M3U8).

A history gives play *order* and local file paths, but no times. The files themselves are
gold: they can be matched against the recording to get exact times (see audio.matcher), and
their embedded tags often carry ISRCs, MusicBrainz/Discogs IDs and labels.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path

from setlister.models import TrackRef
from setlister.textnorm import similarity, split_artist_title


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _num(text: str | None) -> float | None:
    try:
        return float(text) if text and text.strip() else None
    except ValueError:
        return None


def _mmss(text: str | None) -> float | None:
    if not text or ":" not in text:
        return None
    parts = [int(p) for p in text.strip().split(":")]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return float(secs)


def parse_history_txt(path: Path) -> list[TrackRef]:
    """rekordbox 'Export a playlist to a file for KUVO' / history .txt (tab separated)."""
    rows = list(csv.DictReader(io.StringIO(_read_text(path)), delimiter="\t"))
    tracks = []
    for row in rows:
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        tracks.append(
            TrackRef(
                artist=row.get("Artist", ""),
                title=row.get("Track Title", "") or row.get("Title", ""),
                album=row.get("Album") or None,
                label=row.get("Label") or None,
                bpm=_num(row.get("BPM")),
                key=row.get("Key") or None,
                duration=_mmss(row.get("Time")),
            )
        )
    return tracks


def parse_m3u(path: Path) -> list[TrackRef]:
    tracks: list[TrackRef] = []
    pending: TrackRef | None = None
    for line in _read_text(path).splitlines():
        line = line.strip()
        if not line or line == "#EXTM3U":
            continue
        if line.startswith("#EXTINF:"):
            dur, _, name = line[len("#EXTINF:") :].partition(",")
            artist, title = split_artist_title(name)
            pending = TrackRef(artist=artist, title=title, duration=_num(dur))
        elif not line.startswith("#"):
            t = pending or TrackRef(title=Path(line).stem)
            t.path = line
            tracks.append(t)
            pending = None
    return tracks


def merge(primary: list[TrackRef], extra: list[TrackRef]) -> list[TrackRef]:
    """Combine two exports of the same history (e.g. .txt has BPM/key, .m3u8 has paths)."""
    if not primary:
        return extra
    out = []
    used: set[int] = set()
    for i, a in enumerate(primary):
        best, best_j = 0.0, None
        for j, b in enumerate(extra):
            if j in used:
                continue
            s = similarity(a.display, b.display) + (0.2 if i == j else 0.0)
            if s > best:
                best, best_j = s, j
        merged = a.model_copy()
        if best_j is not None and best > 0.6:
            used.add(best_j)
            b = extra[best_j]
            for field in TrackRef.model_fields:
                if getattr(merged, field) in (None, "") and getattr(b, field) not in (None, ""):
                    setattr(merged, field, getattr(b, field))
        out.append(merged)
    return out


def load_histories(paths: list[Path]) -> list[TrackRef]:
    tracks: list[TrackRef] = []
    for p in paths:
        parsed = parse_m3u(p) if p.suffix.lower() in (".m3u", ".m3u8") else parse_history_txt(p)
        tracks = merge(tracks, parsed) if tracks else parsed
    return tracks


# --- embedded tags ---------------------------------------------------------------------------

TAG_MAP = {
    "isrc": ("isrc", "tsrc"),
    "musicbrainz_recording_id": ("musicbrainz_trackid", "musicbrainz track id"),
    "label": ("label", "publisher", "organization", "discogs_label", "tpub"),
    "date": ("date", "year", "discogs_released", "originaldate"),
    "discogs_release_id": ("discogs_release_id",),
    "catalog": ("catalognumber", "discogs_catalog"),
    "url": ("www", "url", "woar", "purl"),
    "album": ("album",),
    "artist": ("artist",),
    "title": ("title",),
    "comment": ("comment",),
}


def read_tags(path: Path) -> dict[str, str]:
    """Embedded tags via ffprobe (no extra dependency; works for AIFF/WAV/FLAC/MP3/M4A)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            check=True,
            capture_output=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    raw = {k.lower(): v for k, v in json.loads(out).get("format", {}).get("tags", {}).items()}
    tags: dict[str, str] = {}
    for name, keys in TAG_MAP.items():
        for k in keys:
            if raw.get(k):
                tags[name] = str(raw[k]).strip()
                break
    return tags


def enrich_from_tags(track: TrackRef, tags: dict[str, str]) -> TrackRef:
    t = track.model_copy()
    t.isrc = t.isrc or tags.get("isrc")
    t.musicbrainz_recording_id = t.musicbrainz_recording_id or tags.get("musicbrainz_recording_id")
    t.discogs_release_id = t.discogs_release_id or tags.get("discogs_release_id")
    t.label = t.label or tags.get("label")
    t.album = t.album or tags.get("album")
    if not t.year and tags.get("date", "")[:4].isdigit():
        t.year = int(tags["date"][:4])
    return t
