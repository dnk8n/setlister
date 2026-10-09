from pathlib import Path

from setlister.sources.rekordbox import load_histories, parse_history_txt, parse_m3u

FIX = Path(__file__).parent / "fixtures"


def test_txt_utf16():
    t = parse_history_txt(FIX / "history.txt")
    assert len(t) == 3
    assert (
        t[1].artist == "Mr G" and t[1].bpm == 125.98 and t[1].duration == 547 and t[1].key == "2A"
    )


def test_m3u():
    t = parse_m3u(FIX / "history.m3u8")
    assert (
        t[2].title == "Deep Burnt"
        and t[2].path.endswith("Deep Burnt.aiff")
        and t[2].duration == 676
    )


def test_merge_keeps_bpm_and_path():
    t = load_histories([FIX / "history.txt", FIX / "history.m3u8"])
    assert len(t) == 3
    assert all(x.path and x.bpm for x in t)
