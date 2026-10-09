"""Where to buy or listen: only pages confirmed to be the track. A site with no confirmed
page is left out rather than given a search link, so every link in the output is real."""

from __future__ import annotations

import logging

from setlister.models import Link, TrackRef

log = logging.getLogger(__name__)


def find_links(
    track: TrackRef,
    sites: list[str],
    *,
    resolve_exact: bool = True,
    known: list[Link] | None = None,
    discogs_release_id: str | None = None,
) -> list[Link]:
    """At most one confirmed link per site, in the order of `sites`."""
    from setlister.links import bandcamp, discogs, video_sites

    by_site: dict[str, Link] = {}
    for link in known or []:
        if link.exact and link.site not in by_site:
            by_site[link.site] = link
    if not resolve_exact or not (track.artist and track.title):
        return [by_site[s] for s in sites if s in by_site]
    finders = {
        "bandcamp": lambda: bandcamp.find(track),
        "discogs": lambda: discogs.find(track, release_id=discogs_release_id),
        "soundcloud": lambda: video_sites.find(track, "soundcloud"),
        "youtube": lambda: video_sites.find(track, "youtube"),
    }
    for site in sites:
        if site in by_site:
            continue
        if site not in finders:
            continue
        try:
            link = finders[site]()
        except Exception as e:  # one flaky site must not sink the run
            log.debug("link lookup failed on %s: %s", site, e)
            link = None
        if link:
            by_site[site] = link
    return [by_site[s] for s in sites if s in by_site]
