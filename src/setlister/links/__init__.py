"""Where to buy or listen: exact pages when they can be found, search links otherwise."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from setlister.models import Link, TrackRef

log = logging.getLogger(__name__)

SEARCH_URLS = {
    "bandcamp": "https://bandcamp.com/search?q={q}&item_type=t",
    "discogs": "https://www.discogs.com/search/?q={q}&type=all",
    "soundcloud": "https://soundcloud.com/search/sounds?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "beatport": "https://www.beatport.com/search?q={q}",
}


def search_link(site: str, track: TrackRef) -> Link:
    q = quote_plus(f"{track.artist} {track.title}".strip())
    return Link(site=site, url=SEARCH_URLS[site].format(q=q), exact=False)


def find_links(
    track: TrackRef,
    sites: list[str],
    *,
    resolve_exact: bool = True,
    known: list[Link] | None = None,
    discogs_release_id: str | None = None,
) -> list[Link]:
    """One link per site; exact pages preferred, search URLs as fallback."""
    from setlister.links import bandcamp, discogs, video_sites

    by_site: dict[str, Link] = {}
    for link in known or []:
        if link.exact and link.site not in by_site:
            by_site[link.site] = link
    if resolve_exact and not track.artist and not track.title:
        resolve_exact = False
    finders = {
        "bandcamp": lambda: bandcamp.find(track),
        "discogs": lambda: discogs.find(track, release_id=discogs_release_id),
        "soundcloud": lambda: video_sites.find(track, "soundcloud"),
        "youtube": lambda: video_sites.find(track, "youtube"),
    }
    for site in sites:
        if site in by_site:
            continue
        link = None
        if resolve_exact and site in finders:
            try:
                link = finders[site]()
            except Exception as e:  # one flaky site must not sink the run
                log.debug("link lookup failed on %s: %s", site, e)
        by_site[site] = link or search_link(site, track)
    order = sites + [s for s in by_site if s not in sites]
    return [by_site[s] for s in order if s in by_site]
