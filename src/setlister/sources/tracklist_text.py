"""Find tracklists in free text: video descriptions, chapter titles and comments.

This is the cheapest signal of all. Uploaders and fans often post the whole answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from setlister.textnorm import split_artist_title
from setlister.timefmt import parse_timestamp

_TS = r"(?:\d{1,2}:)?\d{1,2}:\d{2}"
# "00:00 Artist - Title", "[00:00] Artist - Title", "1. 00:00 Artist - Title", "00:00 - Artist - Title"
_LEAD = re.compile(
    rf"^\s*(?:\d{{1,3}}[.)]\s*)?[\[(]?(?P<ts>{_TS})[\])]?\s*[-–—|:.]?\s*(?P<rest>.+?)\s*$"
)
# "Artist - Title (00:00)" / "Artist - Title 00:00"
_TRAIL = re.compile(rf"^\s*(?:\d{{1,3}}[.)]\s*)?(?P<rest>.+?)\s*[\[(]?(?P<ts>{_TS})[\])]?\s*$")
# "1. Artist - Title" (no time)
_NUMBERED = re.compile(r"^\s*(?P<n>\d{1,3})\s*[.)]\s*(?P<rest>.+?\s[-–—]\s.+?)\s*$")


@dataclass
class TextTrack:
    artist: str
    title: str
    time: float | None
    line: str


def _clean(rest: str) -> str:
    rest = re.sub(r"^\s*[-–—|:.]\s*", "", rest)
    return rest.strip().strip("\"'")


def parse_timestamped(text: str, *, min_entries: int = 3) -> list[TextTrack]:
    """Lines carrying a timestamp and an 'Artist - Title'. Returns [] if it doesn't look like a
    tracklist (fewer than `min_entries` lines, or times going backwards)."""
    found: list[TextTrack] = []
    for line in text.splitlines():
        m = _LEAD.match(line) or _TRAIL.match(line)
        if not m:
            continue
        rest = _clean(m.group("rest"))
        if len(rest) < 3 or rest.lower() in {"intro", "outro"}:
            continue
        artist, title = split_artist_title(rest)
        found.append(TextTrack(artist, title, parse_timestamp(m.group("ts")), line.strip()))
    if len(found) < min_entries:
        return []
    times = [t.time for t in found]
    if sum(b < a for a, b in zip(times, times[1:], strict=False)) > len(times) // 5:
        return []  # not monotonic: probably a list of comments at different times
    return found


def parse_numbered(text: str, *, min_entries: int = 3) -> list[TextTrack]:
    """'1. Artist - Title' lists without times (order only)."""
    found = []
    for line in text.splitlines():
        m = _NUMBERED.match(line)
        if m and not re.search(_TS, m.group("rest")):
            artist, title = split_artist_title(m.group("rest"))
            found.append(TextTrack(artist, title, None, line.strip()))
    return found if len(found) >= min_entries else []


def chapters_to_tracks(chapters: list[dict]) -> list[TextTrack]:
    out = []
    for ch in chapters or []:
        title = (ch.get("title") or "").strip()
        artist, t = split_artist_title(title)
        if title and title.lower() not in {"intro", "outro", "<untitled chapter 1>"}:
            out.append(TextTrack(artist, t, float(ch.get("start_time", 0)), title))
    return out
