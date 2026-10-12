"""Bandcamp has no public API. Its own search box calls a small JSON endpoint, which is
tried first; the HTML search page is the fallback. Both are unofficial and may change."""

from __future__ import annotations

import logging

import requests
from bs4 import BeautifulSoup

from setlister.models import Link, TrackRef
from setlister.textnorm import similarity

log = logging.getLogger(__name__)

# A browser-like agent: Bandcamp serves an empty or blocked page to unknown clients.
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 setlister/0.1",
}
AUTOCOMPLETE = "https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic"


def find(track: TrackRef, min_similarity: float = 0.8) -> Link | None:
    q = f"{track.artist} {track.title}"
    for search in (_autocomplete, _search_page):
        try:
            hits = search(q)
        except (requests.RequestException, ValueError) as e:
            log.debug("bandcamp %s failed: %s", search.__name__, e)
            continue
        log.debug("bandcamp %s: %d results for %r", search.__name__, len(hits), q)
        url = best_match(track, hits, min_similarity)
        if url:
            return Link(site="bandcamp", url=url, exact=True)
    return None


def best_match(track: TrackRef, hits: list[tuple[str, str, str]], min_similarity: float):
    """hits are (artist, title, url); the artist and the title must both match."""
    for artist, title, url in hits[:8]:
        if (
            similarity(f"{artist} - {title}", track.display) >= min_similarity
            or (similarity(artist, track.artist) >= 0.8 and similarity(title, track.title) >= 0.85)
        ) and url:
            return url.split("?")[0]
    return None


def _autocomplete(q: str) -> list[tuple[str, str, str]]:
    r = requests.post(
        AUTOCOMPLETE,
        json={"search_text": q, "search_filter": "t", "full_page": False, "fan_id": None},
        headers=UA,
        timeout=15,
    )
    r.raise_for_status()
    results = (r.json().get("auto") or {}).get("results") or r.json().get("results") or []
    return [
        (h.get("band_name", ""), h.get("name", ""), h.get("item_url_path", ""))
        for h in results
        if h.get("type") == "t"
    ]


def _search_page(q: str) -> list[tuple[str, str, str]]:
    r = requests.get(
        "https://bandcamp.com/search", params={"q": q, "item_type": "t"}, headers=UA, timeout=15
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    hits = []
    for item in soup.select("li.searchresult"):
        heading = item.select_one(".heading a")
        if not heading:
            continue
        subhead = item.select_one(".subhead")
        sub = " ".join(subhead.get_text(" ", strip=True).split()) if subhead else ""
        by = sub.rsplit(" by ", 1)[-1] if " by " in sub else sub.removeprefix("by ")
        hits.append((by.strip(), heading.get_text(" ", strip=True), heading.get("href", "")))
    return hits
