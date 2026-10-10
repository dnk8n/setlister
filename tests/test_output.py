from setlister.models import Entry, Link, Setlist, TrackRef
from setlister.output import check_paste, description_text, mixcloud_tracklist


def entry(start, artist, title, conf=0.9, links=()):
    return Entry(
        start=start,
        end=start + 300,
        track=TrackRef(artist=artist, title=title),
        confidence=conf,
        links=[Link(site=s, url=u, exact=True) for s, u in links],
    )


def setlist(n=12, url_len=60):
    entries = [
        entry(
            2 + i * 300,
            f"Artist {i}",
            f"Track <{i}>",
            conf=0.5 + i / 100,
            links=[
                ("discogs", "https://d.example/" + "x" * url_len),
                ("bandcamp", "https://b.example/1"),
            ],
        )
        for i in range(n)
    ]
    entries.append(Entry(start=n * 300 + 2, end=None, track=TrackRef(), confidence=0))
    return Setlist(url="u", duration=n * 300 + 400, entries=entries)


def test_youtube_text_passes_its_own_checks_and_has_one_link_per_track():
    text = description_text(setlist(), sites=["bandcamp", "discogs"])
    assert check_paste(text, "youtube") == []
    assert text.splitlines()[1].startswith("0:00:00 ")  # chapters start at zero
    assert text.count("https://b.example/1") == 12 and "d.example" not in text
    assert "<" not in text and ">" not in text


def test_links_are_dropped_from_least_certain_tracks_to_fit():
    sl = setlist(n=40, url_len=120)
    text = description_text(sl, limit=4000, sites=["discogs"])
    assert len(text) <= 4000 and check_paste(text, "soundcloud") == []
    assert "Artist 39 - Track (39): https://d.example" in text  # most certain keeps its link
    assert "Artist 0 - Track (0): " not in text


def test_mixcloud_lines_are_artist_title_hhmmss_without_unknowns():
    lines = mixcloud_tracklist(setlist(n=3)).splitlines()
    assert lines == [
        "Artist 0 - Track (0) - 00:00:02",
        "Artist 1 - Track (1) - 00:05:02",
        "Artist 2 - Track (2) - 00:10:02",
    ]


def test_youtube_check_catches_chapter_problems():
    assert "first timestamp is not 00:00, so no chapters" in check_paste(
        "0:05 A\n1:00 B\n2:00 C\n", "youtube"
    )
    assert check_paste("0:00 A\n0:05 B\n2:00 C\n", "youtube")


def test_folder_names_stay_unique_for_uploads_with_similar_titles():
    from setlister.output import folder_name

    a = folder_name(
        "The Adventures of Pepper and Pumpernickl - Knisper Festival 2026 full 2hr DJ set",
        "omxI8_CGaSs",
    )
    b = folder_name(
        "The Adventures of Pepper and Pumpernickl - Knisper Festival 2026 highlight reel",
        "d__gZC1iRnI",
    )
    assert a != b and a.endswith("-omxI8_CGaSs") and not a.split("-omxI8")[0].endswith("-")
