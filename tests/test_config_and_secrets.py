import pytest

from setlister.config import Config
from setlister.secrets import _register, redact


def test_config_defaults_are_free_and_local():
    c = Config()
    assert c.notes.model.startswith("ollama/")
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
