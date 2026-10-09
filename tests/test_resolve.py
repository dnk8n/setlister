from setlister.models import Evidence, Setlist, Source, TrackRef
from setlister.output import description_text
from setlister.resolve import pick_in_order, resolve


def ev(artist, title, start, end, conf, src=Source.LOCAL_MATCH, order=None):
    return Evidence(
        track=TrackRef(artist=artist, title=title),
        source=src,
        confidence=conf,
        start=start,
        end=end,
        order=order,
    )


def test_merge_same_track_from_two_sources():
    entries = resolve(
        [
            ev("A", "One", 0, 300, 0.6),
            ev("A", "One", 10, 290, 0.5, Source.DESCRIPTION),
            ev("B", "Two", 280, 600, 0.9),
        ],
        duration=600,
    )
    assert [e.track.title for e in entries] == ["One", "Two"]
    assert entries[0].confidence > 0.6 and len(entries[0].sources) == 2
    assert entries[0].end == entries[1].start == 290  # split mid-transition


def test_conflict_becomes_contender_and_gap_becomes_id():
    entries = resolve(
        [
            ev("A", "One", 0, 300, 0.9),
            ev("X", "Wrong", 50, 250, 0.3, Source.ACOUSTID),
            ev("B", "Two", 600, 900, 0.8),
        ],
        duration=900,
    )
    assert entries[0].contenders[0].title == "Wrong"
    assert entries[1].is_unknown and entries[1].start == 300 and entries[1].end == 600


def test_pick_in_order_rejects_out_of_order_placements():
    options = [
        [ev("A", "1", 4000, 4300, 0.45)],
        [ev("B", "2", 100, 400, 0.6)],
        [ev("C", "3", 400, 700, 0.7)],
    ]
    chosen = pick_in_order(options)
    assert [e.track.title for e in chosen] == ["2", "3"]


def test_description_text_has_zero_start_and_id_guesses():
    entries = resolve([ev("A", "One", 20, 300, 0.9), ev("B", "Two", 300, 600, 0.3)], duration=600)
    text = description_text(Setlist(url="u", entries=entries, duration=600), min_conf=0.5)
    lines = text.splitlines()
    assert lines[1].startswith("00:00 A - One")
    assert "ID? (B - Two)" in lines[2]


def test_same_track_tolerates_accents_and_extra_credits():
    from setlister.resolve import same_track

    a = TrackRef(artist="Pépé Bradock & The Grand Brûlé's Choir", title="Deep Burnt", isrc="X1")
    b = TrackRef(artist="Pepe Bradock", title="Deep Burnt", isrc="Y2")
    assert same_track(a, b)
    assert not same_track(a, TrackRef(artist="Someone Else", title="Deep Burnt"))


def test_zero_length_rows_are_folded_into_neighbours():
    entries = resolve(
        [
            ev("Label", "Sliver", 0, 3, 0.4),
            ev("A", "One", 3, 300, 0.9),
            ev("B", "Two", 300, 600, 0.9),
        ],
        duration=600,
    )
    starts = [e.start for e in entries]
    assert starts == sorted(set(starts)) and starts[0] == 0
    assert all((e.end or 600) - e.start >= 20 for e in entries)
    assert entries[0].track.title == "One" and entries[0].contenders[0].title == "Sliver"
