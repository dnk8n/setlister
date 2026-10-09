import pytest

from setlister.config import Config
from setlister.secrets import _register, redact


def test_config_defaults_are_free_and_local():
    c = Config()
    assert c.notes.model.startswith("ollama/")
    assert c.notes.llm is False  # opt-in: slow on a laptop
    assert c.identify.shazam is True  # free, chosen by the maintainer


def test_config_rejects_secrets():
    with pytest.raises(ValueError, match="secret"):
        Config.model_validate({"identify": {"acoustid_api_key": "abc"}})


def test_config_rejects_unknown_keys():
    with pytest.raises(ValueError):
        Config.model_validate({"identify": {"typo": True}})


def test_redaction():
    _register("supersecretvalue123")
    assert redact("token=supersecretvalue123!") == "token=***!"


def test_notes_without_llm_are_facts_and_make_no_calls(monkeypatch):
    import sys

    from setlister.config import NotesConfig
    from setlister.models import TrackRef
    from setlister.notes import write_note

    monkeypatch.setitem(sys.modules, "litellm", None)  # importing it would fail loudly
    note, how = write_note(
        TrackRef(artist="A", title="B", label="M-Plant", year=2014), {}, NotesConfig()
    )
    assert how == "facts" and note == "Released in 2014 on M-Plant."
