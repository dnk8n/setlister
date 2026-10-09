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
        # A release is confirmed only if its artist matches and it has the track on it.
        artist = rel.title.split(" - ", 1)[0]
        if similarity(artist, track.artist) < 0.8 and not _various_with(rel, track):
            continue
        if any(similarity(t.title, track.title) >= 0.85 for t in rel.tracklist):
            return Link(site="discogs", url=rel.url, exact=True)
    return None


def _various_with(rel, track: TrackRef) -> bool:
    """Compilations are titled "Various - …"; then the track's own artist must match."""
    if not rel.title.lower().startswith("various"):
        return False
    for t in rel.tracklist:
        names = " ".join(a.name for a in getattr(t, "artists", []) or [])
        if names and similarity(names, track.artist) >= 0.8:
            return True
    return False


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
