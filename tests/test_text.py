from setlister.sources.tracklist_text import chapters_to_tracks, parse_numbered, parse_timestamped
from setlister.textnorm import norm, similarity, split_artist_title
from setlister.timefmt import format_timestamp, parse_timestamp

DESCRIPTION = """Recorded live at Knisper.

Tracklist:
00:00 Pépé Bradock - Deep Burnt
[05:37] Mr. G - Daily Prayer
1. 09:19 Amy Douglas, Luke Solomon - Light You Up
13:36 – Oscar Sulley & The Uhuru Dance Band - Bukom Mashie (JKriv Edit)
1:02:03 ID - ID

Follow us on instagram
"""


def test_parse_timestamped_description():
    tracks = parse_timestamped(DESCRIPTION)
    assert [t.time for t in tracks] == [0, 337, 559, 816, 3723]
    assert tracks[0].artist == "Pépé Bradock" and tracks[0].title == "Deep Burnt"
    assert tracks[3].artist.startswith("Oscar Sulley")


def test_trailing_timestamps():
    text = "Artist A - One (0:00)\nArtist B - Two (4:10)\nArtist C - Three (9:59)"
    assert [t.time for t in parse_timestamped(text)] == [0, 250, 599]


def test_random_comment_is_not_a_tracklist():
    assert parse_timestamped("that drop at 12:30 though!!") == []
    assert parse_timestamped("30:00 wow\n10:00 yes\n50:00 no\n05:00 hm") == []


def test_numbered_untimed():
    text = "1. A - One\n2. B - Two\n3. C - Three"
    assert [t.title for t in parse_numbered(text)] == ["One", "Two", "Three"]


def test_chapters():
    tr = chapters_to_tracks(
        [{"title": "Intro", "start_time": 0}, {"title": "X - Y", "start_time": 60}]
    )
    assert len(tr) == 1 and tr[0].artist == "X" and tr[0].time == 60


def test_timefmt_roundtrip():
    assert parse_timestamp("1:02:03") == 3723
    assert format_timestamp(3723) == "1:02:03"
    assert format_timestamp(65) == "01:05"
    assert format_timestamp(65, force_hours=True) == "0:01:05"


def test_norm_and_similarity():
    assert (
        norm("Pépé Bradock & The Grand Brûlé's Choir") == "pepe bradock and the grand brule s choir"
    )
    assert similarity("Mr G - Transient", "Mr. G - Transient") > 0.9
    assert similarity("Mr G - Transient", "Floorplan - Never Grow Old") < 0.4
    assert split_artist_title("A – B - C") == ("A", "B - C")
