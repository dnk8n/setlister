from types import SimpleNamespace

from setlister import links
from setlister.links import discogs, video_sites
from setlister.models import Link, TrackRef

TRACK = TrackRef(artist="DFRA", title="Dancin'")


def test_sites_without_a_confirmed_page_are_left_out(monkeypatch):
    monkeypatch.setattr("setlister.links.bandcamp.find", lambda t: None)
    monkeypatch.setattr(
        "setlister.links.video_sites.find",
        lambda t, site: (
            Link(site=site, url=f"https://{site}.example/x", exact=True)
            if site == "youtube"
            else None
        ),
    )
    monkeypatch.setattr("setlister.links.discogs.find", lambda t, release_id=None: None)
    out = links.find_links(TRACK, ["bandcamp", "discogs", "soundcloud", "youtube"])
    assert [link.site for link in out] == ["youtube"]
    assert all(link.exact for link in out)


def test_unidentified_tracks_get_no_links():
    assert links.find_links(TrackRef(), ["bandcamp", "youtube"]) == []


def test_video_hit_must_name_the_artist(monkeypatch):
    hit = {"title": "Dancin' (Original Mix)", "uploader": "Some Label", "webpage_url": "u"}
    monkeypatch.setattr(video_sites, "search_first", lambda q, site: hit)
    assert video_sites.find(TRACK, "youtube") is None
    hit["uploader"] = "DFRA"
    assert video_sites.find(TRACK, "youtube").url == "u"


def test_discogs_release_must_carry_the_track(monkeypatch):
    def rel(title, tracks, url):
        return SimpleNamespace(
            title=title, url=url, tracklist=[SimpleNamespace(title=t) for t in tracks]
        )

    page = [
        rel("DFRA - Other EP", ["Something Else"], "wrong"),
        rel("DFRA - Dancin' EP", ["Intro", "Dancin'"], "right"),
    ]
    client = SimpleNamespace(search=lambda **kw: SimpleNamespace(page=lambda n: page))
    monkeypatch.setattr(discogs, "client", lambda: client)
    assert discogs.find(TRACK).url == "right"
    page.pop()
    assert discogs.find(TRACK) is None


def test_video_hit_of_a_different_version_is_rejected(monkeypatch):
    hit = {"title": "DFRA - Dancin' (Someone Remix)", "uploader": "x", "webpage_url": "u"}
    monkeypatch.setattr(video_sites, "search_first", lambda q, site: hit)
    assert video_sites.find(TRACK, "youtube") is None
    remix = TrackRef(artist="DFRA", title="Dancin' (Someone Remix)")
    assert video_sites.find(remix, "youtube").url == "u"


def test_bandcamp_autocomplete_results_are_matched_on_artist_and_title(monkeypatch):
    from setlister.links import bandcamp

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "auto": {
                    "results": [
                        {
                            "type": "b",
                            "name": "Asa Tate",
                            "item_url_path": "https://a.bandcamp.com",
                        },
                        {
                            "type": "t",
                            "name": "Replica (Edit)",
                            "band_name": "Someone",
                            "item_url_path": "https://x.bandcamp.com/track/replica-edit",
                        },
                        {
                            "type": "t",
                            "name": "Replica",
                            "band_name": "Asa Tate",
                            "item_url_path": "https://asatate.bandcamp.com/track/replica?from=search",
                        },
                    ]
                }
            }

    monkeypatch.setattr(bandcamp.requests, "post", lambda *a, **k: Resp())
    link = bandcamp.find(TrackRef(artist="Asa Tate", title="Replica"))
    assert link.url == "https://asatate.bandcamp.com/track/replica"
