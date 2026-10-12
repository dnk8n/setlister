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
    try:
        if track.musicbrainz_recording_id:
            return _lookup(track.musicbrainz_recording_id)
        if track.isrc:
            _throttle()
            recs = mb.get_recordings_by_isrc(track.isrc, includes=["artists"]).get("isrc", {})
            for r in recs.get("recording-list", [])[:1]:
                return _lookup(r["id"])
        if track.title:
            _throttle()
            res = mb.search_recordings(recording=track.title, artist=track.artist, limit=10)
            matches = [r for r in res.get("recording-list", []) if is_same(r, track)]
            if matches:
                # Several recordings often match (EP, single, DJ-mix compilation): prefer one
                # on a proper EP/single/album, then the earliest, so runs agree.
                best = min(matches, key=lambda r: (_release_rank(best_release(r)), _first_date(r)))
                return _lookup(best["id"])
    except mb.WebServiceError as e:
        log.debug("musicbrainz: %s", e)
    return None


RECORDING_INCLUDES = ["artists", "releases", "url-rels", "recording-rels", "isrcs", "tags"]
RELEASE_INCLUDES = ["release-groups"]


def _lookup(recording_id: str) -> dict:
    """The recording, with its releases' release groups (EP, single, DJ-mix...). A recording
    lookup can't include release groups, so its releases are browsed for them."""
    _throttle()
    rec = mb.get_recording_by_id(recording_id, includes=RECORDING_INCLUDES)["recording"]
    try:
        _throttle()
        res = mb.browse_releases(recording=recording_id, includes=RELEASE_INCLUDES, limit=100)
        if res.get("release-list"):
            rec["release-list"] = res["release-list"]
    except mb.WebServiceError as e:
        log.debug("musicbrainz releases: %s", e)
    return rec


def is_same(rec: dict, track: TrackRef) -> bool:
    """Both artist and title must match closely: 'Raz Fresco - Vanilla Skies' is not
    'Dan Fresco - Vanilla'."""
    artist_ok = similarity(rec.get("artist-credit-phrase", ""), track.artist) >= 0.9
    return artist_ok and similarity(rec.get("title", ""), track.title) >= 0.85


def _first_date(rec: dict) -> str:
    dates = [r["date"] for r in _proper(rec.get("release-list", [])) if r.get("date")]
    return min(dates, default="9999") + rec.get("id", "")


PRIMARY_RANK = {"EP": 0, "Single": 1, "Album": 2}


def _release_rank(release: dict | None) -> int:
    """EP first, then single, then album. A release group with secondary types (DJ-mix,
    Compilation, Live, Broadcast...) is someone else's mix the track appears on."""
    if not release:
        return 99
    group = release.get("release-group") or {}
    rank = PRIMARY_RANK.get(group.get("primary-type") or group.get("type"), 5)
    if group.get("secondary-type-list"):
        rank += 10
    if release.get("status") not in (None, "Official"):
        rank += 20
    return rank


def best_release(rec: dict) -> dict | None:
    releases = rec.get("release-list", [])
    return min(releases, key=lambda r: (_release_rank(r), r.get("date") or "9999"), default=None)


def _proper(releases: list[dict]) -> list[dict]:
    """Releases on the artist's own EP/single/album; all of them if there are none."""
    own = [r for r in releases if _release_rank(r) < 10]
    return own or releases


def facts_and_links(rec: dict) -> tuple[dict, list[Link]]:
    facts: dict = {
        "musicbrainz_id": rec.get("id"),
        "title": rec.get("title"),
        "artist": rec.get("artist-credit-phrase"),
    }
    releases = sorted(
        rec.get("release-list", []), key=lambda r: (_release_rank(r), r.get("date") or "9999")
    )
    dates = sorted(r["date"] for r in _proper(releases) if r.get("date"))
    if dates:
        facts["first_release_date"] = dates[0]
    facts["releases"] = [r.get("title") for r in releases[:5]]
    best = releases[0] if releases else None
    group = (best or {}).get("release-group") or {}
    if group.get("primary-type"):
        facts["release_type"] = group["primary-type"]
    facts["tags"] = [t["name"] for t in rec.get("tag-list", [])[:8]]
    samples = sampled(rec)
    if samples:
        facts["samples"] = [t.display for t in samples]
    # Link the release group of the artist's own EP/single/album when there is one, not a
    # DJ-mix compilation the recording also appears on.
    if group.get("id") and _release_rank(best) < 10:
        url = f"https://musicbrainz.org/release-group/{group['id']}"
    else:
        url = f"https://musicbrainz.org/recording/{rec['id']}"
    links = [Link(site="musicbrainz", url=url, exact=True)]
    for rel in rec.get("url-relation-list", []):
        url = rel.get("target", "")
        for host, site in SITE_HOSTS.items():
            if host in url:
                links.append(Link(site=site, url=url, exact=True))
    return facts, links


def sampled(rec: dict) -> list[TrackRef]:
    """Recordings this one samples ("samples material", read forwards; backwards means
    it was sampled by the other recording)."""
    out = []
    for rel in rec.get("recording-relation-list", []):
        if rel.get("type") != "samples material" or rel.get("direction") == "backward":
            continue
        target = rel.get("recording") or {}
        if target.get("title"):
            out.append(
                TrackRef(artist=target.get("artist-credit-phrase", ""), title=target["title"])
            )
    return out
