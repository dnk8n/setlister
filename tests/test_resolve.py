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


def test_low_confidence_rows_are_left_out_of_the_list():
    rejected = []
    entries = resolve(
        [ev("A", "One", 20, 300, 0.9), ev("B", "Two", 300, 600, 0.3)],
        duration=600,
        rejected=rejected,
    )
    text = description_text(Setlist(url="u", entries=entries, duration=600), min_conf=0.5)
    lines = text.splitlines()
    assert lines[1].startswith("00:00 A - One")
    assert lines[2] == "05:00 ID"
    assert "Two" not in text and [r.track.title for r in rejected] == ["Two"]


def test_short_plays_are_penalised_except_at_the_edges():
    rejected = []
    entries = resolve(
        [
            ev("Edge", "Cut", 0, 50, 0.9),  # cut off by the recording start: kept
            ev("A", "One", 50, 400, 0.9),
            ev("Brief", "Blip", 400, 440, 0.9),  # 40 s mid-set: x0.3 -> dropped
            ev("B", "Two", 440, 800, 0.9),
        ],
        duration=800,
        rejected=rejected,
    )
    assert [e.track.title for e in entries] == ["Cut", "One", "Two"]
    assert rejected[0].track.title == "Blip" and rejected[0].confidence < 0.5


def test_same_track_tolerates_accents_and_extra_credits():
    from setlister.resolve import same_track

    a = TrackRef(artist="Pépé Bradock & The Grand Brûlé's Choir", title="Deep Burnt", isrc="X1")
    b = TrackRef(artist="Pepe Bradock", title="Deep Burnt", isrc="Y2")
    assert same_track(a, b)
    assert not same_track(a, TrackRef(artist="Someone Else", title="Deep Burnt"))


def test_zero_length_rows_are_folded_into_neighbours():
    entries = resolve(
        [
            ev("Label", "Sliver", 0, 3, 0.6),
            ev("A", "One", 3, 300, 0.9),
            ev("B", "Two", 300, 600, 0.9),
        ],
        duration=600,
    )
    starts = [e.start for e in entries]
    assert starts == sorted(set(starts)) and starts[0] == 0
    assert all((e.end or 600) - e.start >= 20 for e in entries)
    assert entries[0].track.title == "One" and entries[0].contenders[0].title == "Sliver"


def test_clips_keep_short_rows_without_the_short_play_penalty():
    evidence = [
        ev("A", "One", 0, 12, 0.8),
        ev("B", "Two", 12, 22, 0.8),
        ev("C", "Three", 22, 34, 0.8),
    ]
    rows = resolve(evidence, duration=34, clip=True)
    assert [r.track.title for r in rows] == ["One", "Two", "Three"]
    assert all(r.confidence == 0.8 for r in rows)


def test_local_paths_never_reach_the_output():
    from setlister.models import Entry, Setlist, TrackRef

    t = TrackRef(artist="A", title="B", path="/Users/someone/dj/music/x.aiff")
    sl = Setlist(url="u", entries=[Entry(start=0, track=t, confidence=0.9)])
    assert "/Users/" not in sl.model_dump_json()


def test_shazam_and_acoustid_agreeing_lifts_a_short_play_over_the_bar():
    alone = resolve([ev("A", "One", 100, 150, 0.6, Source.SHAZAM)], duration=600)
    assert all(e.is_unknown for e in alone)  # 50 s, one system: penalised and left out
    agreed = resolve(
        [
            ev("A", "One", 100, 150, 0.4, Source.SHAZAM),
            ev("A", "One", 104, 150, 0.3, Source.ACOUSTID),
        ],
        duration=600,
    )
    named = [e for e in agreed if not e.is_unknown]
    assert named and named[0].confidence >= 0.9


def test_a_sample_source_heard_inside_a_track_becomes_a_footnote():
    entries = resolve(
        [
            ev("Floorplan", "Never Grow Old (Re-plant)", 0, 31, 0.6, Source.SHAZAM),
            ev("Aretha Franklin", "Never Grow Old", 8, 20, 0.4, Source.SHAZAM),
        ],
        duration=31,
        clip=True,
    )
    assert [e.track.artist for e in entries] == ["Floorplan"]
    assert entries[0].samples[0].track.artist == "Aretha Franklin"
    assert entries[0].samples[0].source == "heard in the mix"


def test_a_recogniser_naming_a_track_from_the_djs_history_counts_as_agreement():
    rows = [ev("A", "One", 100, 150, 0.6, Source.SHAZAM)]
    played = [TrackRef(artist="A", title="One")]
    named = [e for e in resolve(rows, duration=600, played=played) if not e.is_unknown]
    assert named and named[0].confidence >= 0.9


def test_a_long_window_hit_on_the_original_corroborates_a_reel_piece():
    from setlister.pipeline import group_hits

    t = TrackRef(artist="Occibel", title="Let It Roll")
    hits = [(30.0, 42.0, t, 0.8, Source.SHAZAM), (30.0, 42.0, t, 0.8, Source.SHAZAM)]
    (g,) = group_hits(hits)
    assert (g.start, g.end) == (30.0, 42.0) and g.confidence > 0.5


def test_mashup_hits_count_for_half_and_lose_to_the_set_track():
    entries = resolve(
        [
            ev("VOIDSAINT", "Mercy x Show Me Love x Feel Just Right", 40, 52, 0.73, Source.SHAZAM),
            ev("Jamie Unknown", "I Wanna", 40, 52, 0.6, Source.ORIGINAL_SET),
        ],
        duration=120,
        clip=True,
    )
    named = [e for e in entries if not e.is_unknown]
    assert named[0].track.title == "I Wanna"


def test_reel_pieces_inherit_the_full_sets_track(tmp_path):
    from setlister.audio.matcher import AlignmentSegment
    from setlister.config import Config
    from setlister.models import Entry
    from setlister.pipeline import inherit_from_set, save_set_timeline

    original = tmp_path / "set.wav"
    original.write_bytes(b"x")
    cfg = Config()
    cfg.cache_dir = tmp_path / "cache"
    save_set_timeline(
        original,
        [
            Entry(
                start=2895,
                end=3094,
                track=TrackRef(artist="Jamie Unknown", title="I Wanna"),
                confidence=0.8,
            ),
            Entry(start=3094, end=3300, track=TrackRef(), confidence=0.0),
        ],
        cfg,
    )
    seg = AlignmentSegment(online_start=40, online_end=52, rate=1.0, offset=2907)  # 48:27
    (ev_,) = inherit_from_set(original, [seg], cfg)
    assert ev_.track.title == "I Wanna" and ev_.source == Source.ORIGINAL_SET
    assert (round(ev_.start), round(ev_.end)) == (40, 52)


def test_recogniser_runs_are_cut_back_at_pieces_of_other_tracks():
    from setlister.pipeline import respect_pieces

    run = ev("Oscar Sulley", "Bukom Mashie", 0, 32, 0.7, Source.SHAZAM)
    pieces = [
        ev("Tommy Atkins", "Intro", 0, 8, 0.8, Source.ORIGINAL_SET),
        ev("Oscar Sulley", "Bukom Mashie", 8, 24, 0.8, Source.ORIGINAL_SET),
        ev("UR", "Transition", 24, 32, 0.8, Source.ORIGINAL_SET),
    ]
    (cut,) = respect_pieces([run], pieces)
    assert (cut.start, cut.end) == (8, 24)
