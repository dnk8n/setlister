"""MusicBrainz lookups (free, no key; 1 request/second). Used to confirm identities and to
harvest facts and links (Bandcamp, Discogs, SoundCloud, YouTube URLs are often attached)."""

from __future__ import annotations

import logging
import time

import musicbrainzngs as mb

from setlister import __version__
from setlister.models import Link, TrackRef
from setlister.textnorm import similarity

log = logging.getLogger(__name__)
mb.set_useragent("setlister", __version__, "https://github.com/dnk8n/setlister")
_last = 0.0

SITE_HOSTS = {
    "bandcamp.com": "bandcamp",
    "discogs.com": "discogs",
    "soundcloud.com": "soundcloud",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "beatport.com": "beatport",
}


def _throttle() -> None:
    global _last
    wait = 1.05 - (time.monotonic() - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.monotonic()


def find_recording(track: TrackRef) -> dict | None:
    includes = ["artists", "releases", "url-rels", "isrcs", "tags"]
    try:
        if track.musicbrainz_recording_id:
            _throttle()
            return mb.get_recording_by_id(track.musicbrainz_recording_id, includes=includes)[
                "recording"
            ]
        if track.isrc:
            _throttle()
            recs = mb.get_recordings_by_isrc(track.isrc, includes=["artists"]).get("isrc", {})
            for r in recs.get("recording-list", [])[:1]:
                _throttle()
                return mb.get_recording_by_id(r["id"], includes=includes)["recording"]
        if track.title:
            _throttle()
            res = mb.search_recordings(recording=track.title, artist=track.artist, limit=10)
            matches = [r for r in res.get("recording-list", []) if is_same(r, track)]
            if matches:
                # Several recordings often match (album, single, compilation): take the
                # earliest release so facts are the same on every run.
                best = min(matches, key=_first_date)
                _throttle()
                return mb.get_recording_by_id(best["id"], includes=includes)["recording"]
    except mb.WebServiceError as e:
        log.debug("musicbrainz: %s", e)
    return None


def is_same(rec: dict, track: TrackRef) -> bool:
    """Both artist and title must match closely: 'Raz Fresco - Vanilla Skies' is not
    'Dan Fresco - Vanilla'."""
    artist_ok = similarity(rec.get("artist-credit-phrase", ""), track.artist) >= 0.9
    return artist_ok and similarity(rec.get("title", ""), track.title) >= 0.85


def _first_date(rec: dict) -> str:
    dates = [r["date"] for r in rec.get("release-list", []) if r.get("date")]
    return min(dates, default="9999") + rec.get("id", "")


def facts_and_links(rec: dict) -> tuple[dict, list[Link]]:
    facts: dict = {
        "musicbrainz_id": rec.get("id"),
        "title": rec.get("title"),
        "artist": rec.get("artist-credit-phrase"),
    }
    releases = rec.get("release-list", [])
    dates = sorted(r["date"] for r in releases if r.get("date"))
    if dates:
        facts["first_release_date"] = dates[0]
    facts["releases"] = [r.get("title") for r in releases[:5]]
    facts["tags"] = [t["name"] for t in rec.get("tag-list", [])[:8]]
    links = [
        Link(site="musicbrainz", url=f"https://musicbrainz.org/recording/{rec['id']}", exact=True)
    ]
    for rel in rec.get("url-relation-list", []):
        url = rel.get("target", "")
        for host, site in SITE_HOSTS.items():
            if host in url:
                links.append(Link(site=site, url=url, exact=True))
    return facts, links
