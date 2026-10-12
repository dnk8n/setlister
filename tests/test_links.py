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
    monkeypatch.setattr(video_sites, "search", lambda q, site, n: [hit])
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
    monkeypatch.setattr(video_sites, "search", lambda q, site, n: [hit])
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


def test_official_upload_beats_a_fan_upload_which_is_the_fallback(monkeypatch):
    fan = {"title": "DFRA - Dancin'", "uploader": "fan123", "webpage_url": "fan"}
    official = {"title": "Dancin'", "uploader": "DFRA", "webpage_url": "official"}
    monkeypatch.setattr(video_sites, "search", lambda q, site, n: [fan, official])
    assert video_sites.find(TRACK, "soundcloud").url == "official"
    monkeypatch.setattr(video_sites, "search", lambda q, site, n: [fan])
    assert video_sites.find(TRACK, "soundcloud").url == "fan"


def test_musicbrainz_sample_relations_are_read_forwards_only():
    from setlister.identify.musicbrainz import sampled

    rec = {
        "recording-relation-list": [
            {
                "type": "samples material",
                "recording": {"title": "Never Grow Old", "artist-credit-phrase": "Aretha Franklin"},
            },
            {"type": "samples material", "direction": "backward", "recording": {"title": "Later"}},
            {"type": "remix", "recording": {"title": "Other"}},
        ]
    }
    assert [t.display for t in sampled(rec)] == ["Aretha Franklin - Never Grow Old"]


def test_mashups_and_sped_up_rips_are_never_used(monkeypatch):
    sosa = TrackRef(artist="Sosa UK", title="Bring It Back")
    mashup = {
        "title": "Sosa UK - Bring It Back x Renegade Master (DJ C Blend) TIK TOK BASS BOOSTED",
        "uploader": "realxrc",
        "webpage_url": "https://soundcloud.com/realxrc/sosa-uk-bring-it-back-x-renegade-master",
    }
    padded = {"title": "Sosa UK - Bring It Back x Renegade Master", "uploader": "a", "url": "p"}
    plain = {"title": "Sosa UK - Bring It Back (Original Mix)", "uploader": "b", "url": "ok"}
    monkeypatch.setattr(video_sites, "search", lambda q, site, n: [mashup, padded, plain])
    assert video_sites.find(sosa, "soundcloud").url == "ok"
    monkeypatch.setattr(video_sites, "search", lambda q, site, n: [mashup, padded])
    assert video_sites.find(sosa, "soundcloud") is None


def test_musicbrainz_prefers_the_ep_over_a_dj_mix_compilation():
    from setlister.identify.musicbrainz import facts_and_links

    rec = {
        "id": "rec1",
        "title": "Replica",
        "artist-credit-phrase": "Asa Tate",
        "release-list": [
            {
                "title": "Some DJ Mix",
                "date": "2019-01-01",
                "status": "Official",
                "release-group": {
                    "id": "mix",
                    "primary-type": "Broadcast",
                    "secondary-type-list": ["DJ-mix", "Live"],
                },
            },
            {
                "title": "Replica EP",
                "date": "2020-05-01",
                "status": "Official",
                "release-group": {"id": "ep", "primary-type": "EP"},
            },
        ],
    }
    facts, links = facts_and_links(rec)
    assert links[0].url == "https://musicbrainz.org/release-group/ep"
    assert facts["releases"][0] == "Replica EP" and facts["release_type"] == "EP"
    assert facts["first_release_date"] == "2020-05-01"  # the mix's earlier date is not the release
