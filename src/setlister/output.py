"""Write results to out/<set>/: paste-ready description text, a rich Markdown tracklist,
machine-readable JSON, and instructions for publishing."""

from __future__ import annotations

import logging
import re
from itertools import pairwise
from pathlib import Path

from setlister.models import Entry, Setlist
from setlister.timefmt import format_timestamp, parse_timestamp

log = logging.getLogger(__name__)

SITE_NAMES = {
    "bandcamp": "Bandcamp",
    "discogs": "Discogs",
    "soundcloud": "SoundCloud",
    "youtube": "YouTube",
    "musicbrainz": "MusicBrainz",
    "beatport": "Beatport",
}


def slug(text: str, max_len: int = 50) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    if len(s) > max_len:
        s = s[:max_len].rsplit("-", 1)[0]  # cut at a word boundary
    return s or "set"


def folder_name(title: str, video_id: str | None) -> str:
    """Readable and unique: uploads of one event often share most of their title."""
    return f"{slug(title)}-{video_id}" if video_id else slug(title)


def short_label(entry: Entry) -> str:
    """For the paste-ready list: a name, or a plain ID. Guesses live in tracklist.md."""
    return "ID" if entry.is_unknown else entry.track.display


def label(entry: Entry, min_conf: float) -> str:
    if entry.is_unknown:
        if entry.contenders:
            return "ID? (" + " / ".join(c.display for c in entry.contenders) + ")"
        return "ID"
    if entry.confidence < min_conf:
        alts = [entry.track] + entry.contenders
        return "ID? (" + " / ".join(a.display for a in alts[:4]) + ")"
    return entry.track.display


# Paste targets. Limits are from each platform's help pages (checked 2026-10):
# YouTube 5,000 characters, chapters need 00:00 first, 3+ timestamps in ascending order and
# 10 s+ each (support.google.com/youtube/answer/57404 and /9884579). SoundCloud 4,000
# characters, plain text, no HTML (help.soundcloud.com article 31560037965979). Mixcloud's
# tracklist box takes "Artist Name - Track Title - HH:MM:SS" lines (help.mixcloud.com
# article 360004053959).
PLATFORMS = {"youtube": 5000, "soundcloud": 4000}
YOUTUBE_MIN_CHAPTER = 10.0
FOOTER = (
    "Tracklist by setlister (https://github.com/dnk8n/setlister). "
    "ID = not identified yet; corrections welcome."
)


def _clean(text: str) -> str:
    """YouTube rejects descriptions with angle brackets; keep every target plain text."""
    return text.replace("<", "(").replace(">", ")").replace("\n", " ").strip()


def _best_link(entry: Entry, sites: list[str]) -> str | None:
    by_site = {link.site: link.url for link in entry.links if link.exact}
    for site in sites + list(by_site):
        if site in by_site:
            return by_site[site]
    return None


def description_text(
    sl: Setlist, min_conf: float = 0.5, *, limit: int = 5000, sites: list[str] | None = None
) -> str:
    """Timestamped list (YouTube chapters) followed by one confirmed link per track.

    Links sit in their own section so chapter titles stay short and clean. If the text would
    exceed `limit`, links are dropped from the least certain tracks first.
    """
    sites = sites or list(SITE_NAMES)
    hours = bool(sl.duration and sl.duration >= 3600)
    rows = []
    for i, e in enumerate(sl.entries):
        start = 0.0 if i == 0 else e.start  # chapters must start at 00:00
        rows.append(f"{format_timestamp(start, force_hours=hours)} {_clean(short_label(e))}")
    numbered = [
        (i, e, _best_link(e, sites)) for i, e in enumerate(sl.entries, 1) if not e.is_unknown
    ]
    links = {i: url for i, _, url in numbered if url}
    by_certainty = sorted((e.confidence, i) for i, e, url in numbered if url)

    def build() -> str:
        body = ["Tracklist:", *rows]
        if links:
            body += ["", "Links:"]
            body += [
                f"{i}. {_clean(e.track.display)}: {links[i]}" for i, e, _ in numbered if i in links
            ]
        body += ["", FOOTER]
        return "\n".join(body) + "\n"

    text = build()
    while len(text) > limit and by_certainty:
        links.pop(by_certainty.pop(0)[1])
        text = build()
    return text


def mixcloud_tracklist(sl: Setlist) -> str:
    """Mixcloud's paste box: "Artist Name - Track Title - HH:MM:SS". Unknown rows are left
    out (Mixcloud uses the list to credit and license tracks); add them by hand if you like."""
    lines = []
    for e in sl.entries:
        if e.is_unknown:
            continue
        h, rem = divmod(int(round(e.start)), 3600)
        ts = f"{h:02d}:{rem // 60:02d}:{rem % 60:02d}"
        lines.append(f"{_clean(e.track.artist)} - {_clean(e.track.title)} - {ts}")
    return "\n".join(lines) + "\n"


def check_paste(text: str, platform: str) -> list[str]:
    """Problems that would make a platform reject or misread the pasted text."""
    problems = []
    limit = PLATFORMS.get(platform)
    if limit and len(text) > limit:
        problems.append(f"{len(text)} characters, over {platform}'s {limit}")
    if "<" in text or ">" in text:
        problems.append("contains < or >")
    if platform == "youtube":
        stamps = []
        for line in text.splitlines():
            first = line.split(" ", 1)[0]
            try:
                stamps.append(parse_timestamp(first))
            except ValueError:
                continue
        if len(stamps) < 3:
            problems.append("fewer than 3 timestamps, so no chapters")
        elif stamps[0] != 0:
            problems.append("first timestamp is not 00:00, so no chapters")
        elif any(b - a < YOUTUBE_MIN_CHAPTER for a, b in pairwise(stamps)):
            problems.append("a chapter is shorter than 10 s or out of order, so no chapters")
    return problems


def markdown(sl: Setlist, min_conf: float) -> str:
    hours = bool(sl.duration and sl.duration >= 3600)
    out = [f"# {sl.title or sl.url}", "", f"Source: {sl.url}", ""]
    if sl.offset_note:
        out += [f"> {sl.offset_note}", ""]
    for i, e in enumerate(sl.entries, 1):
        end = f"–{format_timestamp(e.end, force_hours=hours)}" if e.end else ""
        out.append(
            f"## {i}. {format_timestamp(e.start, force_hours=hours)}{end} · {label(e, min_conf)}"
        )
        out.append("")
        meta = []
        if not e.is_unknown:
            meta.append(f"confidence {e.confidence:.0%}")
        if e.sources:
            meta.append("from " + ", ".join(s.value for s in e.sources))
        if e.track.label:
            meta.append(e.track.label)
        if e.track.year:
            meta.append(str(e.track.year))
        if meta:
            out += ["*" + " · ".join(meta) + "*", ""]
        if e.links:
            out += [
                " · ".join(
                    f"[{SITE_NAMES.get(link.site, link.site)}]({link.url})" for link in e.links
                ),
                "",
            ]
        if e.note:
            out += [e.note, ""]
            if e.note_sources:
                out += ["<sub>Sources: " + ", ".join(e.note_sources) + "</sub>", ""]
        if e.contenders and not e.is_unknown and e.confidence >= min_conf:
            out += ["Other candidates: " + "; ".join(c.display for c in e.contenders), ""]
    if sl.rejected:
        out += [
            "## Low-confidence detections (left out of the tracklist)",
            "",
            "Probably mismatches (e.g. heard for a minute or less); listed for checking.",
            "",
        ]
        for e in sl.rejected:
            end = f"–{format_timestamp(e.end, force_hours=hours)}" if e.end else ""
            srcs = ", ".join(x.value for x in e.sources)
            out.append(
                f"- {format_timestamp(e.start, force_hours=hours)}{end} {e.track.display} "
                f"({e.confidence:.0%}, {srcs})"
            )
        out.append("")
    return "\n".join(out)


INSTRUCTIONS = """# Publishing this tracklist

Each paste file is plain text checked against its platform's rules: length limit, no
`<` or `>`, and for YouTube the chapter rules (first timestamp 00:00, at least three,
ascending, each chapter at least 10 seconds). If a check failed, `setlister` said so
when it wrote the files. Every link is a confirmed page for that exact track; tracks
without one have no link.

| File | Where it goes |
|---|---|
| `description.youtube.txt` | YouTube video description (5,000 characters max) |
| `description.soundcloud.txt` | SoundCloud track description (4,000 characters max) |
| `tracklist.mixcloud.txt` | Mixcloud upload, "paste tracklist" box |
| `tracklist.md` | the full version: every link, confidence, a note per track |
| `setlist.json` | everything, machine readable |

## YouTube

1. YouTube Studio, then Content, then the video, then Details.
2. Paste `description.youtube.txt` into the description, below any text you already have.
   Keep the total under 5,000 characters.
3. Save. The timestamps become chapters (YouTube may still decline chapters on some
   videos, e.g. with active strikes).

## SoundCloud

Paste `description.soundcloud.txt` into the track's description. SoundCloud shows plain
text only; URLs appear as links.

## Mixcloud

In the upload's tracklist step choose to paste a tracklist and paste
`tracklist.mixcloud.txt` (one `Artist - Title - HH:MM:SS` per line). Unidentified rows are
left out; Mixcloud uses the list to credit and license tracks. Mixcloud links tracks to
its own pages, so no external links go here.

## Corrections

Edit `setlist.json`, then run `setlister render path/to/setlist.json` to rewrite these
files without analysing any audio.
"""


def write_all(
    sl: Setlist, directory: Path, min_conf: float, sites: list[str] | None = None
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    pastes = {
        "description.youtube.txt": (
            "youtube",
            description_text(sl, min_conf, limit=5000, sites=sites),
        ),
        "description.soundcloud.txt": (
            "soundcloud",
            description_text(sl, min_conf, limit=4000, sites=sites),
        ),
        "tracklist.mixcloud.txt": ("mixcloud", mixcloud_tracklist(sl)),
    }
    for name, (platform, text) in pastes.items():
        (directory / name).write_text(text)
        for problem in check_paste(text, platform):
            log.warning("%s: %s", name, problem)
    (directory / "tracklist.md").write_text(markdown(sl, min_conf))
    (directory / "setlist.json").write_text(sl.model_dump_json(indent=2))
    (directory / "README.md").write_text(INSTRUCTIONS)
    return directory
