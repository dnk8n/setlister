# setlister

Turn a link to a DJ or live set into a **timestamped, linked, annotated tracklist** you can
paste straight into the post's description.

```text
$ setlister run https://www.youtube.com/watch?v=… --original my-recording.wav -H HISTORY.m3u8
› Reading the online post (title, description, chapters, comments)
› History: 15 tracks, 15 local files available
› Locating 15 history tracks in the recording
› Fingerprinting 23 uncovered moments with acoustid
› Finding links and writing track notes
Done: 21 tracks identified, 3 unknown. See out/knisper-2026/README.md for how to publish.
```

```text
Tracklist:
0:00:00 Tommy Atkins - If It Ain't Broke
0:01:13 ID? (Pépé Bradock & The Grand Brûlé's Choir - Deep Burnt)
0:05:19 Mr. G - Daily Prayer
0:09:20 Amy Douglas, Luke Solomon, Queen Rose - Light You Up
…
```

## How it works

Setlister uses **the cheapest information first**, because it often already holds the
answer, and only does heavy audio work for what is still unknown.

| stage | what | cost |
|---|---|---|
| text | tracklists in the description, chapters and top comments ([yt-dlp]) | seconds |
| history | your DJ software history (rekordbox `.txt`/`.m3u8`) and the tags of the files it lists (ISRC, MusicBrainz and Discogs IDs, labels) | seconds |
| audio match | finds each of your local files inside the recording, even when you changed its tempo; aligns your original recording with a trimmed online copy | ~10 s per track on a laptop CPU |
| recognise | fingerprints the stretches nothing explained (Shazam via shazamio, [AcoustID]) | network calls |
| resolve | merges all evidence, keeps play order consistent, gives confidence and up to 3 contenders when unsure (`ID?`) | instant |
| enrich | confirmed Bandcamp, Discogs, SoundCloud and YouTube pages (the artist's own upload preferred, a fan upload only if nothing else); sample sources; a short note per track from [MusicBrainz]/Discogs facts; optionally (`--llm-notes`) written up by your [Claude Code] login, a local LLM ([Ollama] + Qwen) or any [LiteLLM] provider | network calls |

Everything works with **free** services by default. Paid ones are opt-in (see
[docs/providers.md](docs/providers.md)).

## Quick start (macOS)

```bash
brew install ffmpeg chromaprint          # chromaprint gives `fpcalc` for AcoustID
git clone https://github.com/dnk8n/setlister && cd setlister
uv venv && uv pip install -e '.[llm]'    # or: python -m venv .venv && pip install -e '.[llm]'
setlister doctor                         # tells you what's missing and what each piece unlocks
setlister config set acoustid_key        # free keys go to your macOS Keychain, never to files
setlister config set discogs_token
ollama pull qwen3:8b                     # optional, for --llm-notes (slow on a laptop);
                                         # or notes.model = "claude-code/haiku" if you use Claude Code
```

Then:

```bash
# Just a link (downloads audio only if it needs to)
setlister run https://www.youtube.com/watch?v=…

# With your own recording (no big download; handles an online copy that was trimmed)
setlister run URL --original "~/sets/2026-10-09.wav"

# Back to back: pass every history you have, one -H per file
setlister run URL --original rec.wav -H "HISTORY me.txt" -H "HISTORY me.m3u8" -H partner.m3u8

# Offline: only your files, no network at all
setlister run --original rec.wav -H history.m3u8 --offline
```

Results land in `out/<set-name>/` with a README explaining where to paste what.

## Principles

- **Cheap before expensive.** Text and metadata first; downloads and fingerprinting only for
  what is still unexplained.
- **Honest output.** Every row carries a confidence. Below the threshold it reads
  `ID? (A / B / C)`, never a confident guess. Two audio systems (Shazam, AcoustID, a
  local file match) naming the same track lifts it to at least 90%; a play of a minute or
  less heard by only one is probably a mismatch. Sample sources are footnoted, marked
  "possibly" unless MusicBrainz records them.
- **Reuse over reinvention.** yt-dlp, librosa, Chromaprint/AcoustID, MusicBrainz, the Discogs
  client, LiteLLM and Ollama do the heavy lifting. New code is limited to what didn't exist:
  tempo-tolerant matching of known tracks inside a mix, evidence resolution, and the glue.
- **Secrets never touch the repo.** Keys live in the OS keychain (or a gitignored `.env`).
  `setlister.toml` refuses anything that looks like a secret. gitleaks runs as a pre-commit
  and pre-push hook and in CI, so a leaked key fails the push.
- **No media in git.** Audio, video and images are refused anywhere but `docs/` (hook + CI).

## Contributing

New recognisers, link sources and DJ-software importers are very welcome. Start with
[CONTRIBUTING.md](CONTRIBUTING.md) and [docs/architecture.md](docs/architecture.md); the
roadmap lives in [docs/roadmap.md](docs/roadmap.md).

## License

MIT. Dependencies keep their own licenses: everything required is permissive, except that
Chromaprint (`fpcalc`) is LGPL and used as a separate program, and ffmpeg is used as a separate
program too. Setlister does not bundle or link GPL/AGPL code.

[yt-dlp]: https://github.com/yt-dlp/yt-dlp
[AcoustID]: https://acoustid.org
[MusicBrainz]: https://musicbrainz.org
[Ollama]: https://ollama.com
[Claude Code]: https://code.claude.com
[LiteLLM]: https://github.com/BerriAI/litellm
