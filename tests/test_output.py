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


def test_youtube_text_names_platforms_per_track_and_lists_their_urls():
    text = description_text(setlist(), sites=["bandcamp", "discogs"])
    assert check_paste(text, "youtube") == []
    lines = text.splitlines()
    assert lines[1] == "0:00:00 Artist 0 - Track (0) (Bandcamp | Discogs)"  # chapters at zero
    assert "Artist 0 - Track (0): https://b.example/1 https://d.example/" in text
    assert "<" not in text and ">" not in text


def test_ids_leave_the_tracklist_for_an_unsure_paragraph():
    sl = setlist(n=3)
    sl.entries.insert(
        2,
        Entry(
            start=500,
            end=560,
            track=TrackRef(),
            confidence=0,
            contenders=[TrackRef(artist="X", title="Maybe")],
        ),
    )
    text = description_text(sl, sites=["bandcamp"])
    tracklist = text.split("\n\n")[0]
    assert "ID" not in tracklist
    assert "08:20-09:20 ID? (X - Maybe)" in text.split("Unsure")[1]


def test_links_are_dropped_from_least_certain_tracks_to_fit():
    sl = setlist(n=40, url_len=120)
    text = description_text(sl, limit=4000, sites=["discogs"])
    assert len(text) <= 4000 and check_paste(text, "soundcloud") == []
    assert "Artist 39 - Track (39): https://d.example" in text  # most certain keeps it
    assert "Artist 0 - Track (0): " not in text
    assert "Artist 0 - Track (0) (Discogs)" not in text  # names follow the links left


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


def test_sample_footnotes_are_listed_and_dropped_before_links():
    from setlister.models import Sample

    sl = setlist(n=3)
    sl.entries[1].samples = [
        Sample(track=TrackRef(artist="Aretha Franklin", title="Never Grow Old"), source="x")
    ]
    text = description_text(sl, sites=["bandcamp"])
    assert (
        "Samples:\nArtist 1 - Track (1) samples Aretha Franklin - Never Grow Old (possibly" in text
    )
    tight = description_text(sl, limit=len(text) - 1, sites=["bandcamp"])
    assert "Samples:" not in tight and tight.count("https://b.example/1") == 3


def test_short_rows_share_a_chapter_so_youtube_keeps_chapters():
    from setlister.output import chapters

    sl = Setlist(
        url="u",
        duration=120,
        entries=[
            entry(0, "A", "One"),
            entry(52, "Floorplan", "Never Grow Old"),
            entry(56, "Gerd Janson", "London Town"),
            entry(115, "B", "Two"),
        ],
    )
    assert chapters(sl) == [
        (0.0, 1, "A - One"),
        (52, 2, "Floorplan - Never Grow Old / Gerd Janson - London Town / B - Two"),
    ]
    assert check_paste(description_text(sl), "youtube") == [
        "fewer than 3 timestamps, so no chapters"
    ]
