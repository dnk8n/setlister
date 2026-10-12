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
PLATFORM_ORDER = ["bandcamp", "discogs", "musicbrainz", "soundcloud", "youtube", "beatport"]


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
FOOTER = "Tracklist by setlister (https://github.com/dnk8n/setlister). Corrections welcome."


def _clean(text: str) -> str:
    """YouTube rejects descriptions with angle brackets; keep every target plain text."""
    return text.replace("<", "(").replace(">", ")").replace("\n", " ").strip()


def description_text(
    sl: Setlist, min_conf: float = 0.5, *, limit: int = 5000, sites: list[str] | None = None
) -> str:
    """Timestamped list (YouTube chapters) with the platforms each track was found on, then
    the links themselves, then the unsure stretches.

    Plain-text platforms can't make "Bandcamp" clickable, so the names go next to the track
    and the URLs (which become links) in a block below. If the text would exceed `limit`,
    sample footnotes go first, then MusicBrainz links, then links of the least certain tracks.
    """
    sites = sites or list(SITE_NAMES)
    hours = bool(sl.duration and sl.duration >= 3600)
    named = [e for e in sl.entries if not e.is_unknown]
    links = {n: track_links(e, sites) for n, e in enumerate(named, 1)}
    samples = {n: sample_line(e) for n, e in enumerate(named, 1) if e.samples}
    by_certainty = [n for _, n in sorted((e.confidence, n) for n, e in enumerate(named, 1))]
    drops = [("sample", n, None) for n in by_certainty if n in samples]
    drops += [("link", n, "musicbrainz") for n in by_certainty]
    drops += [("link", n, site) for n in by_certainty for site in reversed(sites)]
    unsure = unsure_lines(sl, hours)

    def build() -> str:
        rows = []
        for start, n, label in chapters(sl):
            names = " | ".join(SITE_NAMES.get(s, s) for s, _ in links.get(n, []))
            rows.append(
                f"{format_timestamp(start, force_hours=hours)} {_clean(label)}"
                + (f" ({names})" if names else "")
            )
        body = ["Tracklist:", *rows]
        if any(links.values()):
            body += ["", "Links:"]
            body += [
                f"{_clean(named[n - 1].track.display)}: " + " ".join(url for _, url in links[n])
                for n in sorted(links)
                if links[n]
            ]
        if samples:
            body += ["", "Samples:"]
            body += [samples[n] for n in sorted(samples)]
        if unsure:
            body += ["", UNSURE_INTRO, *unsure]
        body += ["", FOOTER]
        return "\n".join(body) + "\n"

    text = build()
    while len(text) > limit and drops:
        kind, n, site = drops.pop(0)
        if kind == "sample":
            samples.pop(n, None)
        else:
            links[n] = [(s, u) for s, u in links[n] if s != site]
        text = build()
    return text


UNSURE_WHY = "often still the track before, a blend or a mic break"
UNSURE_INTRO = f"Unsure ({UNSURE_WHY}):"


def track_links(entry: Entry, sites: list[str]) -> list[tuple[str, str]]:
    """Confirmed (site, url) pairs in platform order."""
    by_site: dict[str, str] = {}
    for link in entry.links:
        if link.exact:
            by_site.setdefault(link.site, link.url)
    order = [s for s in PLATFORM_ORDER if s in sites or s == "musicbrainz"]
    return [(s, by_site[s]) for s in order if s in by_site]


def unsure_lines(sl: Setlist, hours: bool) -> list[str]:
    """Unidentified stretches, kept out of the tracklist: most are not a new track."""
    out = []
    for e in sl.entries:
        if not e.is_unknown:
            continue
        end = f"-{format_timestamp(e.end, force_hours=hours)}" if e.end else ""
        guess = (
            " (" + " / ".join(_clean(c.display) for c in e.contenders) + ")" if e.contenders else ""
        )
        out.append(
            f"{format_timestamp(e.start, force_hours=hours)}{end} ID{'?' if guess else ''}{guess}"
        )
    return out


def sample_line(entry: Entry) -> str:
    """'Floorplan - Never Grow Old samples Aretha Franklin - Never Grow Old (heard in the
    mix)'. Recogniser guesses are marked, so nobody mistakes them for a credit."""
    parts = []
    for s in entry.samples:
        how = "per MusicBrainz" if s.source == "MusicBrainz" else "possibly, heard in the mix"
        parts.append(f"{s.track.display} ({how})")
    return _clean(f"{entry.track.display} samples " + "; ".join(parts))


def chapters(sl: Setlist) -> list[tuple[float, int | None, str]]:
    """(start, track number, label) per chapter, identified tracks only: an unidentified
    stretch stays part of the chapter before it. YouTube needs the first chapter at 00:00
    and drops every chapter if one is under 10 s (reels cut every few seconds), so a short
    row shares a chapter with the next: 'A / B'."""
    named = [e for e in sl.entries if not e.is_unknown]
    out: list[tuple[float, int | None, str]] = []
    if named and named[0].start >= YOUTUBE_MIN_CHAPTER:
        out.append((0.0, None, "Intro"))
    for n, e in enumerate(named, 1):
        start = 0.0 if not out else e.start
        if out and start - out[-1][0] < YOUTUBE_MIN_CHAPTER:
            first, num, label = out[-1]
            out[-1] = (first, num if num is not None else n, _join(label, short_label(e)))
        else:
            out.append((start, n, short_label(e)))
    if len(out) > 1 and sl.duration and sl.duration - out[-1][0] < YOUTUBE_MIN_CHAPTER:
        _, num, label = out.pop()
        first, prev, prev_label = out[-1]
        out[-1] = (first, prev if prev is not None else num, _join(prev_label, label))
    return out


def _join(a: str, b: str) -> str:
    return a if b == a else f"{a} / {b}"


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


def markdown(sl: Setlist, min_conf: float, sites: list[str] | None = None) -> str:
    sites = sites or list(SITE_NAMES)
    hours = bool(sl.duration and sl.duration >= 3600)
    out = [f"# {sl.title or sl.url}", "", f"Source: {sl.url}", ""]
    if sl.offset_note:
        out += [f"> {sl.offset_note}", ""]
    named = [e for e in sl.entries if not e.is_unknown]
    for i, e in enumerate(named, 1):
        end = f"–{format_timestamp(e.end, force_hours=hours)}" if e.end else ""
        found = " | ".join(
            f"[{SITE_NAMES.get(site, site)}]({url})" for site, url in track_links(e, sites)
        )
        out.append(
            f"## {i}. {format_timestamp(e.start, force_hours=hours)}{end} · "
            f"{label(e, min_conf)}" + (f" ({found})" if found else "")
        )
        out.append("")
        meta = [f"confidence {e.confidence:.0%}"]
        if e.sources:
            meta.append("from " + ", ".join(s.value for s in e.sources))
        if e.track.label:
            meta.append(e.track.label)
        if e.track.year:
            meta.append(str(e.track.year))
        out += ["*" + " · ".join(meta) + "*", ""]
        if e.note:
            out += [e.note, ""]
            if e.note_sources:
                out += ["<sub>Sources: " + ", ".join(e.note_sources) + "</sub>", ""]
        if e.samples:
            out += [
                "Samples: " + "; ".join(f"{x.track.display} ({x.source})" for x in e.samples),
                "",
            ]
        if e.contenders and e.confidence >= min_conf:
            out += ["Other candidates: " + "; ".join(c.display for c in e.contenders), ""]
    unsure = unsure_lines(sl, hours)
    if unsure:
        out += ["## Unsure", "", UNSURE_WHY.capitalize() + ".", ""]
        out += [f"- {line}" for line in unsure]
        out.append("")
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
without one have no link. "Samples" footnotes come from MusicBrainz, or are marked
"possibly" when a recogniser heard the source inside the track; check those before posting.
Each track names the platforms it was found on; plain-text descriptions can't make those
names clickable, so the URLs follow in a "Links" block (clickable in `tracklist.md`).
Unidentified stretches are not in the tracklist: most are still the track before, a blend
or a mic break. They are listed under "Unsure" at the end.

| File | Where it goes |
|---|---|
| `description.youtube.txt` | YouTube video description (5,000 characters max) |
| `description.soundcloud.txt` | SoundCloud track description (4,000 characters max) |
| `tracklist.mixcloud.txt` | Mixcloud upload, "paste tracklist" box |
| `tracklist.md` | the full version: every link, confidence, samples, a note per track |
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
    (directory / "tracklist.md").write_text(markdown(sl, min_conf, sites))
    (directory / "setlist.json").write_text(sl.model_dump_json(indent=2))
    (directory / "README.md").write_text(INSTRUCTIONS)
    return directory
