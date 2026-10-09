"""Write results to out/<set>/: paste-ready description text, a rich Markdown tracklist,
machine-readable JSON, and instructions for publishing."""

from __future__ import annotations

import re
from pathlib import Path

from setlister.models import Entry, Setlist
from setlister.timefmt import format_timestamp

SITE_NAMES = {
    "bandcamp": "Bandcamp",
    "discogs": "Discogs",
    "soundcloud": "SoundCloud",
    "youtube": "YouTube",
    "musicbrainz": "MusicBrainz",
    "beatport": "Beatport",
}


def slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", s)[:60] or "set"


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


def description_text(sl: Setlist, min_conf: float) -> str:
    hours = bool(sl.duration and sl.duration >= 3600)
    lines = ["Tracklist:"]
    for e in sl.entries:
        lines.append(f"{format_timestamp(e.start, force_hours=hours)} {short_label(e)}")
    lines += [
        "",
        "Tracklist by setlister (https://github.com/dnk8n/setlister). "
        "ID = not identified yet; corrections welcome.",
    ]
    return "\n".join(lines) + "\n"


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

Files here:

- `description.txt`: paste into the online post's description.
- `tracklist.md`: the full version with links, confidence and a note per track.
- `setlist.json`: everything, machine readable (for re-runs, other tools, corrections).

## YouTube

1. Open YouTube Studio, then Content, then the video, then Details.
2. Paste `description.txt` into the description (keep any text you already have above it).
3. Save. Because the first timestamp is `00:00` and there are at least three, YouTube turns
   the list into chapters automatically (each chapter must be at least 10 seconds long).

## SoundCloud / Mixcloud

- SoundCloud: paste `description.txt` into the track description. Timestamps become
  clickable.
- Mixcloud: use the uploader's tracklist editor (it needs per-track start times; copy them
  from `description.txt`) so tracks are credited and licensed properly.

## Corrections

Edit `setlist.json` (or the description) and re-run with `--from-json` to regenerate the
other files without re-analysing audio.
"""


def write_all(sl: Setlist, directory: Path, min_conf: float) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "description.txt").write_text(description_text(sl, min_conf))
    (directory / "tracklist.md").write_text(markdown(sl, min_conf))
    (directory / "setlist.json").write_text(sl.model_dump_json(indent=2))
    (directory / "README.md").write_text(INSTRUCTIONS)
    return directory
