"""YouTube and SoundCloud: a search hit via yt-dlp, kept only if it names both artist and title."""

from __future__ import annotations

import re

from setlister.models import Link, TrackRef
from setlister.sources.youtube import search_first
from setlister.textnorm import norm


def find(track: TrackRef, site: str) -> Link | None:
    hit = search_first(track.display, site)
    if not hit:
        return None
    title = hit.get("title") or ""
    uploader = hit.get("uploader") or hit.get("channel") or ""
    if norm(track.title) not in norm(title):
        return None
    if not _names_artist(track.artist, f"{uploader} {title}"):
        return None
    if _other_version(title, track.title):
        return None
    url = hit.get("webpage_url") or hit.get("url")
    return Link(site=site, url=url, exact=True) if url else None


_VERSION = re.compile(r"\b(remix|rmx|edit|rework|dub|vip|bootleg|live|cover|remaster)\b")


def _other_version(upload_title: str, track_title: str) -> bool:
    """An upload of a remix or edit is a different record unless the track is that version."""
    extra = norm(upload_title).replace(norm(track_title), " ")
    return bool(_VERSION.search(extra))


def _names_artist(artist: str, text: str) -> bool:
    """True if any of the credited artists appears in the uploader or title."""
    text = norm(text)
    for name in artist.replace(" & ", ",").replace(" x ", ",").split(","):
        if norm(name) and norm(name) in text:
            return True
    return False
