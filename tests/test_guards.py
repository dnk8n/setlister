import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_no_media", Path(__file__).parents[1] / "scripts" / "check_no_media.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_media_outside_docs_is_refused():
    assert guard.offenders(["media/set.WAV", "src/a.py", "docs/img/flow.png", "x/cover.JPG"]) == [
        "media/set.WAV",
        "x/cover.JPG",
    ]


def test_media_in_docs_is_allowed():
    assert guard.offenders(["docs/diagram.svg"]) == []


def test_progress_prints_plain_lines_when_not_a_terminal():
    import io

    from rich.console import Console

    from setlister.progress import track

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    assert list(track(range(20), "Fingerprinting", console, str)) == list(range(20))
    lines = buf.getvalue().splitlines()
    assert len(lines) == 10 and lines[-1].startswith("  Fingerprinting 20/20 · ")
