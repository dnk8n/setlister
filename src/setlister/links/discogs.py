"""Discogs via the official client. Needs a free personal token for search."""

from __future__ import annotations

from setlister import __version__
from setlister.models import Link, TrackRef
from setlister.secrets import get_secret
from setlister.textnorm import similarity


def client():
    import discogs_client

    token = get_secret("discogs_token")
    if not token:
        return None
    return discogs_client.Client(f"setlister/{__version__}", user_token=token)


def find(track: TrackRef, release_id: str | None = None) -> Link | None:
    if release_id:
        return Link(site="discogs", url=f"https://www.discogs.com/release/{release_id}", exact=True)
    d = client()
    if d is None:
        return None
    results = d.search(track=track.title, artist=track.artist, type="release")
    for rel in results.page(1)[:5]:
        if similarity(rel.title, f"{track.artist} - {track.album or track.title}") > 0.5 or any(
            similarity(t.title, track.title) > 0.85 for t in rel.tracklist
        ):
            return Link(site="discogs", url=rel.url, exact=True)
    return None


def facts(url: str) -> dict:
    """Year, label, styles and release notes for a Discogs release URL."""
    d = client()
    if d is None or "/release/" not in url:
        return {}
    rid = int(url.rstrip("/").split("/release/")[1].split("-")[0])
    rel = d.release(rid)
    return {
        "discogs_url": url,
        "year": rel.year,
        "labels": [lab.name for lab in rel.labels],
        "styles": rel.styles,
        "genres": rel.genres,
        "country": rel.country,
        "notes": (rel.notes or "")[:800],
        "credits": [f"{c.name} ({c.role})" for c in (rel.credits or [])][:10],
    }
