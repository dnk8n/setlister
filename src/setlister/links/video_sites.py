"""YouTube and SoundCloud: first search hit via yt-dlp, accepted only if the title matches."""

from __future__ import annotations

from setlister.models import Link, TrackRef
from setlister.sources.youtube import search_first
from setlister.textnorm import norm, similarity


def find(track: TrackRef, site: str, min_similarity: float = 0.7) -> Link | None:
    hit = search_first(track.display, site)
    if not hit:
        return None
    title = hit.get("title") or ""
    uploader = hit.get("uploader") or hit.get("channel") or ""
    score = max(
        similarity(title, track.display), similarity(f"{uploader} - {title}", track.display)
    )
    if score < min_similarity or norm(track.title) not in norm(title):
        return None
    url = hit.get("webpage_url") or hit.get("url")
    return Link(site=site, url=url, exact=True) if url else None
