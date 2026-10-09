# Providers

| provider | used for | cost | needs |
|---|---|---|---|
| yt-dlp | post metadata, comments, audio, YouTube/SoundCloud search | free | – |
| MusicBrainz | confirm identities, facts, links attached to recordings | free | – (1 req/s) |
| AcoustID | fingerprint unknown stretches | free | `fpcalc` + free app key |
| Discogs | release facts and links | free | free personal token |
| Bandcamp | exact track pages (search page parsing; no API) | free | – |
| Shazam (shazamio) | fingerprint unknown stretches; very robust on mixes | free, **unofficial** | on by default; `identify.shazam = false` to opt out |
| Ollama + Qwen 3 | track notes, locally | free | `ollama pull qwen3:8b` |
| Anthropic / OpenAI / … via LiteLLM | track notes | paid | `notes.model = "anthropic/…"`, key in keychain |
| AudD, ACRCloud | fingerprinting | paid | TODO, see roadmap |

Shazam through shazamio is not an official API. It can break or be rate limited, and you are
responsible for complying with its terms. Turn it off with `identify.shazam = false`.

Setting keys: `setlister config set <name>` stores them in the OS keychain. Environment
variables `SETLISTER_<NAME>` (or a gitignored `.env`) also work, which is handy in CI.
