"""User configuration, read from `setlister.toml` (no secrets allowed in it).

Search order: --config PATH, ./setlister.toml, <user config dir>/setlister/setlister.toml.
Every field has a sensible free/offline-first default, so the file is optional.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir
from pydantic import BaseModel, ConfigDict, model_validator

FORBIDDEN_KEY_HINTS = ("token", "secret", "password", "api_key", "apikey")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourcesConfig(_Section):
    youtube_comments: bool = True
    max_comments: int = 300


class AudioConfig(_Section):
    analysis_sr: int = 11025
    # When the online audio is needed but an original file is given, still download? (no)
    download_when_original_given: bool = False
    # Range of playback-speed changes to search when locating a known track in the mix.
    max_tempo_change: float = 0.08


class IdentifyConfig(_Section):
    acoustid: bool = True
    shazam: bool = True  # free but unofficial API, see docs/providers.md
    # Seconds between Shazam requests. Faster gets an IP blocked for hours (seen at 1 s).
    # Answers are cached, so this cost is paid once per set.
    shazam_pace_seconds: float = 4.0
    window_seconds: float = 20.0
    step_seconds: float = 30.0
    max_contenders: int = 3
    # TODO(paid): audd = false, acrcloud = false


class LinksConfig(_Section):
    sites: list[str] = ["bandcamp", "discogs", "soundcloud", "youtube"]
    resolve_exact: bool = (
        True  # look up confirmed pages; false = only links found in the set's own text
    )


class NotesConfig(_Section):
    # Off by default: a local LLM is slow on a laptop. Without it each track still gets a
    # short factual note (year, label, styles). Turn on with `--llm-notes` or llm = true.
    llm: bool = False
    # "claude-code/haiku" uses the Claude Code CLI you are logged in to (no API key).
    # Anything else is a LiteLLM model string: free local Qwen via Ollama (the default,
    # https://ollama.com), or paid APIs such as "anthropic/claude-haiku-5-5".
    model: str = "ollama/qwen3:8b"
    api_base: str | None = None
    max_words: int = 70


class OutputConfig(_Section):
    directory: Path = Path("out")
    min_confidence_to_name: float = 0.5  # below this, show "ID?" plus contenders


class Config(_Section):
    sources: SourcesConfig = SourcesConfig()
    audio: AudioConfig = AudioConfig()
    identify: IdentifyConfig = IdentifyConfig()
    links: LinksConfig = LinksConfig()
    notes: NotesConfig = NotesConfig()
    output: OutputConfig = OutputConfig()
    cache_dir: Path = Path(user_cache_dir("setlister"))

    @model_validator(mode="before")
    @classmethod
    def _no_secrets(cls, data: object) -> object:
        def walk(d: object, path: str = "") -> None:
            if isinstance(d, dict):
                for k, v in d.items():
                    if any(h in str(k).lower() for h in FORBIDDEN_KEY_HINTS):
                        raise ValueError(
                            f"'{path}{k}' looks like a secret. Secrets don't belong in "
                            "setlister.toml: run `setlister config` to store it in your keychain."
                        )
                    walk(v, f"{path}{k}.")

        walk(data)
        return data


def config_paths(explicit: Path | None = None) -> list[Path]:
    if explicit:
        return [explicit]
    return [Path("setlister.toml"), Path(user_config_dir("setlister")) / "setlister.toml"]


def load_config(explicit: Path | None = None) -> tuple[Config, Path | None]:
    for p in config_paths(explicit):
        if p.is_file():
            with p.open("rb") as f:
                return Config.model_validate(tomllib.load(f)), p
    if explicit:
        raise FileNotFoundError(explicit)
    return Config(), None
