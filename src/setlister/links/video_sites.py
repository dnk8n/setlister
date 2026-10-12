"""YouTube and SoundCloud: search hits via yt-dlp, kept only if they name both artist and
title. An upload by a channel named after the artist (theirs, or YouTube's 'Artist - Topic') is preferred; a fan's upload
is used only when no official one turns up."""

from __future__ import annotations

import re

from setlister.models import Link, TrackRef
from setlister.sources.youtube import search
from setlister.textnorm import norm


def find(track: TrackRef, site: str) -> Link | None:
    fallback = None
    for hit in search(track.display, site, 5):
        title = hit.get("title") or ""
        uploader = hit.get("uploader") or hit.get("channel") or ""
        url = hit.get("webpage_url") or hit.get("url")
        if not url or norm(track.title) not in norm(title) or _other_version(title, track.title):
            continue
        if _JUNK.search(norm(f"{title} {url}")):
            continue
        if _names_artist(track.artist, uploader):
            return Link(site=site, url=url, exact=True)
        if fallback is None and _names_artist(track.artist, title) and _plain(title, track):
            fallback = Link(site=site, url=url, exact=True)
    return fallback


# Re-uploads that are not the record as released.
_JUNK = re.compile(
    r"\b(sped up|speed up|slowed|reverb|nightcore|bass boosted|8d|tik ?tok|blend|mash ?up|"
    r"yt1s\w*|mp3|free download|reupload|re upload)\b"
)
_HARMLESS = {"original", "mix", "official", "audio", "video", "hd", "hq", "premiere", "feat", "ft"}


def _plain(upload_title: str, track: TrackRef) -> bool:
    """A fan upload is kept only if its title is just artist and title (plus words like
    'Original Mix'): 'Bring It Back x Renegade Master' is a mashup, not the track."""
    known = set(norm(f"{track.artist} {track.title}").split()) | _HARMLESS
    extra = [w for w in norm(upload_title).split() if w not in known]
    return len(extra) <= 1


_VERSION = re.compile(r"\b(remix|rmx|edit|rework|dub|vip|bootleg|live|cover|remaster)\b")


def _other_version(upload_title: str, track_title: str) -> bool:
    """An upload of a remix or edit is a different record unless the track is that version."""
    extra = norm(upload_title).replace(norm(track_title), " ")
    return bool(_VERSION.search(extra))


def _names_artist(artist: str, text: str) -> bool:
    """True if any of the credited artists appears in the text."""
    text = norm(text)
    for name in artist.replace(" & ", ",").replace(" x ", ",").split(","):
        if norm(name) and norm(name) in text:
            return True
    return False
