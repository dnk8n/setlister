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
