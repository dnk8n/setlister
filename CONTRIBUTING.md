# Contributing

Thanks for helping! Setlister aims to stay small, readable and honest about uncertainty.

## Setup

```bash
brew install ffmpeg chromaprint     # or your platform's equivalent
uv venv && uv pip install -e '.[dev,llm]'
pre-commit install --hook-type pre-commit --hook-type pre-push
pytest
```

## Ground rules

1. **Never commit media** (audio, video, images) except documentation images under `docs/`.
   Tests use synthetic audio generated in code (`tests/conftest.py`), not recordings.
2. **Never commit secrets.** Use `setlister config set …`. The hooks and CI run gitleaks.
3. **Prefer an existing, maintained library** over new code. If you add a dependency, check
   its license is compatible with MIT (no GPL/AGPL linking).
4. **Every source reports confidence.** Don't make a guess look certain.
5. Keep functions short and named for what they do; add a docstring when the *why* isn't obvious.

## Where things live

```
src/setlister/
  cli.py          commands (run, doctor, config, locate)
  doctor.py       configuration checks shown before every run
  config.py       setlister.toml schema (pydantic)
  secrets.py      keychain/env lookup and redaction
  pipeline.py     the stages, in order
  sources/        cheap inputs: yt-dlp metadata, text tracklists, DJ histories + tags
  audio/          features and the matcher (local tracks in a mix, original vs online)
  identify/       recognisers (AcoustID, Shazam) and MusicBrainz
  links/          Bandcamp, Discogs, YouTube, SoundCloud
  notes/          per-track paragraph (LiteLLM; local Ollama by default)
  resolve.py      evidence -> setlist
  output.py       out/<set>/ files
```

## Adding a recogniser

Implement the `Recognizer` protocol in `identify/__init__.py` (`available()` and
`recognize(wav)`), register it in `recognizers()`, add a config flag, a `doctor` check, and
for paid services a `SecretSpec` in `secrets.py`.

## Tests

`pytest` runs offline in seconds. Tests that need the internet are marked
`@pytest.mark.network` and skipped by default (`pytest -m network` to run them).
