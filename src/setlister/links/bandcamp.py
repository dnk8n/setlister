"""Bandcamp has no public API; its search page is simple HTML, parsed with BeautifulSoup."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from setlister.models import Link, TrackRef
from setlister.textnorm import similarity

UA = {"User-Agent": "setlister (+https://github.com/dnk8n/setlister)"}


def find(track: TrackRef, min_similarity: float = 0.8) -> Link | None:
    q = f"{track.artist} {track.title}"
    r = requests.get(
        "https://bandcamp.com/search", params={"q": q, "item_type": "t"}, headers=UA, timeout=15
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for item in soup.select("li.searchresult")[:5]:
        heading = item.select_one(".heading a")
        sub = item.select_one(".subhead")
        if not heading:
            continue
        title = heading.get_text(" ", strip=True)
        by = sub.get_text(" ", strip=True) if sub else ""
        by = by.split(" by ", 1)[-1] if " by " in by else by
        if similarity(f"{by} - {title}", track.display) >= min_similarity:
            url = heading["href"].split("?")[0]
            return Link(site="bandcamp", url=url, exact=True)
    return None
