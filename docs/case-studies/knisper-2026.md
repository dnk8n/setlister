# Case study: Pepper & Pumpernickl at Knisper 2026

A real back-to-back set, run end to end on a MacBook (Apple Silicon). It shows what
setlister finds when it has the full-length original recording and one of the two DJs'
rekordbox history, tested against four online uploads of the same event: two full-length
copies and two short highlight reels.

## Inputs

| Input | How it was passed | Committed? |
|---|---|---|
| Original recording, 1:55:10 WAV (trimmed board recording) | `--original "media/Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV"` | No. Audio never goes in the repo; `media/` is gitignored. |
| rekordbox history of one of the two DJs, 15 tracks (`.txt` and `.m3u8` exports) | `-H "media/HISTORY 2026-10-09.txt" -H "media/HISTORY 2026-10-09.m3u8"` | No (personal library paths). |
| Online copies | the four URLs below | n/a |

Online copies:

| URL | Title on YouTube | Length |
|---|---|---|
| <https://www.youtube.com/watch?v=omxI8_CGaSs> | The Adventures of Pepper and Pumpernickl - Knisper Festival 2026 full 2hr DJ set | 1:55:11 |
| <https://www.youtube.com/watch?v=DOuO45YCyCs> | Pepper & Pumpernickl - Knisper Festival 2026 | 1:53:49 |
| <https://www.youtube.com/watch?v=JZnURn199K0> | The Adventures of Pepper and Pumpernickl - Knisper Festival 2026 highlight reel | 0:31 |
| <https://www.youtube.com/watch?v=d__gZC1iRnI> | The Adventures of Pepper and Pumpernickl - Knisper Festival 2026 highlight reel | 2:01 |

Because only one DJ's history was available, about half the set has to be found by
fingerprinting (Shazam). AcoustID was configured, but the stored key was a user key rather
than an application key, so AcoustID was switched off for these runs (`setlister doctor`
now flags this).

## Commands

Set up once:

```sh
brew install ffmpeg chromaprint uv          # chromaprint provides fpcalc
uv venv -p 3.12 && uv pip install -e '.[dev,llm]'
uv run setlister config set discogs_token   # prompts; stored in the OS keychain
uv run setlister config set acoustid_key    # application key from acoustid.org/new-application
uv run setlister doctor
```

Facts-only notes (the default). Each URL was run on its own:

```sh
uv run setlister run "https://www.youtube.com/watch?v=omxI8_CGaSs" \
  --original "media/Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV" \
  -H "media/HISTORY 2026-10-09.txt" -H "media/HISTORY 2026-10-09.m3u8"
```

The same command with notes written by Claude Haiku through the local Claude Code login.
`setlister.toml` (gitignored) contained:

```toml
[notes]
model = "claude-code/haiku"
```

```sh
uv run setlister run "https://www.youtube.com/watch?v=omxI8_CGaSs" \
  --original "media/Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV" \
  -H "media/HISTORY 2026-10-09.txt" -H "media/HISTORY 2026-10-09.m3u8" \
  --llm-notes
```

## Results per upload

| Upload | Identified | `ID` rows | Left out (< 50%) | Alignment to the original | Run time: first / cached / with Haiku |
|---|---|---|---|---|---|
| omxI8_CGaSs (full) | 22 | 6 | 17 | Same length as the original, so assumed identical (no download) | 10.6 min / 2.7 min / 5.9 min |
| DOuO45YCyCs (full) | 21 | 6 | 16 | Starts 01:21 into the original, 2 cuts (online 1:53:49, original 1:55:10) | – (reuses the cache from the run above, plus a 1:53:49 download) / 2.6 min / 5.4 min |
| JZnURn199K0 (reel, 0:31) | 2 | 0 | 0 | Could not be lined up; the clip was analysed directly (5 s steps) | 24 s / – / 49 s |
| d__gZC1iRnI (reel, 2:01) | 3 | 3 | 3 | Starts 00:47 into the original, 9 cuts | 112 s / – / 87 s |

Where the evidence came from, on the full upload: the rekordbox history placed 11 of its 15
tracks by matching the local audio files against the recording. Shazam was asked about
145 stretches that nothing else explained. The first run took most of its 10.6 minutes
on those requests, at one request every 4 s. Later runs read them from the cache. The
2-hour upload DOuO45YCyCs is correctly missing the first track (Tommy Atkins), because that
track ends at 1:13 in the recording and the upload starts at 01:21.

"Run time" covers the whole pipeline. *First* is a cold Shazam cache. *Cached* is a re-run
where every fingerprint answer comes from disk. *With Haiku* is a cached run plus the
LLM-written notes. That adds about 3 minutes for 21–22 tracks, because Haiku is only called
when there are facts to ground a note in (see below).

### omxI8_CGaSs: `description.youtube.txt`

The SoundCloud file is identical here, because it is under SoundCloud's 4,000-character
limit (this one is 3,216). `tracklist.mixcloud.txt` holds the same rows in Mixcloud's
paste format, `Artist - Title - HH:MM:SS`, without links or `ID` rows.

```text
Tracklist:
0:00:00 Tommy Atkins - If It Ain't Broke
0:01:15 Pepe Bradock - Deep Burnt
0:04:45 Mr. G - Daily Prayer
0:09:20 Amy Douglas, Luke Solomon, Queen Rose - Light You Up
0:13:15 Oscar Sulley & The Uhuru Dance Band - Bukom Mashie (JKriv's King Mashie Edit)
0:19:50 DFRA - Dancin’ feat. Agus Morgavi (House Master Flash Jazzed Up Rework)
0:22:05 Mory Kante - Yeke Yeke (Hardfloor Mix)
0:27:14 ID
0:28:59 Underground Resistance - Transition (D. Tyrone Remix)
0:32:19 Asa Tate - Replica
0:34:46 Sosa UK - Bring It Back
0:39:45 Occibel - Let It Roll
0:44:40 Dan Fresco - Vanilla
0:48:15 Jamie Unknown - I Wanna
0:51:34 Floorplan - Never Grow Old (Re-plant)
0:58:15 Danny Wabbit - Internal Jungle
1:01:05 Shumba Youth / Zed Bias - London Town (4x4 VIP Refix)
1:05:28 ID
1:08:15 Torres De Lara - De Barrio
1:13:15 Known Artist - You Might Wanna (Club Mix)
1:16:45 Bella - Orchestra Spring
1:20:35 ID
1:26:15 Matt Darey & Lost Tribe - Gamemaster
1:28:05 ID
1:33:45 Montezuma - Puxa Vida!
1:38:05 ID
1:43:45 Empire Of The Sun & southstar - We Are The People (southstar Remix)
1:46:05 ID

Links:
1. Tommy Atkins - If It Ain't Broke: https://www.discogs.com/release/192825
2. Pepe Bradock - Deep Burnt: https://soundcloud.com/scottys-67/pepe-bradock-deep-burnt
3. Mr. G - Daily Prayer: https://phoenixg.bandcamp.com/track/daily-prayer-2
4. Amy Douglas, Luke Solomon, Queen Rose - Light You Up: https://djlukesolomon.bandcamp.com/track/light-you-up
5. Oscar Sulley & The Uhuru Dance Band - Bukom Mashie (JKriv's King Mashie Edit): https://jkriv.bandcamp.com/track/bukom-mashie-jkrivs-king-mashie-edit
6. DFRA - Dancin’ feat. Agus Morgavi (House Master Flash Jazzed Up Rework): https://monocturne.bandcamp.com/track/b2-dfra-dancin-feat-agus-morgavi-house-master-flash-jazzed-up-rework
7. Mory Kante - Yeke Yeke (Hardfloor Mix): https://soundcloud.com/themightyming/mory-kante-yeke-yeke-hardfloor
9. Underground Resistance - Transition (D. Tyrone Remix): https://dtyrone.bandcamp.com/track/underground-resistance-transition-d-tyrone-remix
10. Asa Tate - Replica: https://asatate-techsupport.bandcamp.com/track/replica
11. Sosa UK - Bring It Back: https://musicbrainz.org/recording/e91a2b16-d39d-4767-ae19-70dd0cfa1c20
12. Occibel - Let It Roll: https://soundcloud.com/trommelmusic/premiere-a2-occibel-let-it-roll-rld001
13. Dan Fresco - Vanilla: https://danfresco.bandcamp.com/track/vanilla
14. Jamie Unknown - I Wanna: https://shallnotfade.co.uk/track/i-wanna
15. Floorplan - Never Grow Old (Re-plant): https://m-plant.bandcamp.com/track/never-grow-old-re-plant
16. Danny Wabbit - Internal Jungle: https://www.youtube.com/watch?v=z4qNFt6U1oo
20. Known Artist - You Might Wanna (Club Mix): https://known-artist.bandcamp.com/track/you-might-wanna-club-mix
21. Bella - Orchestra Spring: https://sallyc.bandcamp.com/track/orchestra-spring
23. Matt Darey & Lost Tribe - Gamemaster: https://www.youtube.com/watch?v=bboe1FRs2nI
25. Montezuma - Puxa Vida!: https://hotmeal.bandcamp.com/track/puxa-vida
27. Empire Of The Sun & southstar - We Are The People (southstar Remix): https://www.youtube.com/watch?v=qguEGR5BK2k

Tracklist by setlister (https://github.com/dnk8n/setlister). ID = not identified yet; corrections welcome.
```

`tracklist.md` lists 16 detections it left out of the tracklist, each with its time,
confidence and source, so a human can check them. Nearly all of them were heard for
20 seconds and scored 14%. The Sammy Virji detection covered 80 seconds but only reached
39%. It sits inside the 1:05:28 `ID` row and is the strongest hint for that gap.

A sample of `tracklist.md`:

```markdown
## 10. 0:32:19–0:34:35 · Asa Tate - Replica

*confidence 73% · from shazam · Rhythm Section International · 2025*

[Bandcamp](https://asatate-techsupport.bandcamp.com/track/replica) · [SoundCloud](https://soundcloud.com/maslowunknown/asa_tate-replica) · [YouTube](https://www.youtube.com/watch?v=IfVAMaD_scA) · [MusicBrainz](https://musicbrainz.org/recording/3197a775-2611-43a1-858e-e3da46a3675f)

Released in 2025 on Rhythm Section International.

<sub>Sources: MusicBrainz</sub>

Other candidates: Andre Volodin & Karina Smirnova - Cage (Ad Brown Dub Mix); Bass Bumpers - The Music's Got Me (Charismatic Mix); YG IMMA - TAMAM
```

### DOuO45YCyCs: `description.youtube.txt` (tracklist part)

The tracks are the same as above, in the same order, with every timestamp moved back
by 1:21 and then corrected for the two cuts. The Links block is the same apart from the
missing first track.

```text
Tracklist:
0:00:00 Pepe Bradock - Deep Burnt
0:03:24 Mr. G - Daily Prayer
0:07:58 Amy Douglas, Luke Solomon, Queen Rose - Light You Up
0:11:54 Oscar Sulley & The Uhuru Dance Band - Bukom Mashie (JKriv's King Mashie Edit)
0:18:28 DFRA - Dancin’ feat. Agus Morgavi (House Master Flash Jazzed Up Rework)
0:20:44 Mory Kante - Yeke Yeke (Hardfloor Mix)
0:25:52 ID
0:27:38 Underground Resistance - Transition (D. Tyrone Remix)
0:30:57 Asa Tate - Replica
0:33:25 Sosa UK - Bring It Back
0:38:24 Occibel - Let It Roll
0:43:18 Dan Fresco - Vanilla
0:46:54 Jamie Unknown - I Wanna
0:50:12 Floorplan - Never Grow Old (Re-plant)
0:56:54 Danny Wabbit - Internal Jungle
0:59:43 Shumba Youth / Zed Bias - London Town (4x4 VIP Refix)
1:04:07 ID
1:06:54 Torres De Lara - De Barrio
1:11:54 Known Artist - You Might Wanna (Club Mix)
1:15:24 Bella - Orchestra Spring
1:19:14 ID
1:24:54 Matt Darey & Lost Tribe - Gamemaster
1:26:44 ID
1:32:24 Montezuma - Puxa Vida!
1:36:44 ID
1:42:24 Empire Of The Sun & southstar - We Are The People (southstar Remix)
1:44:44 ID
```

### The two highlight reels

The 2-minute reel is lined up with the original piece by piece (9 cuts). Its own audio is
also fingerprinted in 12-second windows. Together these give 3 tracks, all of which are in
the full set. Here is `description.youtube.txt`:

```text
Tracklist:
00:00 Oscar Sulley & The Uhuru Dance Band - Bukom Mashie (Jkriv's King Mashie Edit)
00:32 ID
00:56 Shumba Youth / Zed Bias - London Town (4x4 VIP Refix)
01:08 ID
01:20 Bella - Orchestra Spring
01:42 ID

Links:
1. Oscar Sulley & The Uhuru Dance Band - Bukom Mashie (Jkriv's King Mashie Edit): https://jkriv.bandcamp.com/track/bukom-mashie-jkrivs-king-mashie-edit
5. Bella - Orchestra Spring: https://sallyc.bandcamp.com/track/orchestra-spring

Tracklist by setlister (https://github.com/dnk8n/setlister). ID = not identified yet; corrections welcome.
```

Its `tracklist.mixcloud.txt` is just the three named rows:

```text
Oscar Sulley & The Uhuru Dance Band - Bukom Mashie (Jkriv's King Mashie Edit) - 00:00:00
Shumba Youth / Zed Bias - London Town (4x4 VIP Refix) - 00:00:56
Bella - Orchestra Spring - 00:01:20
```

Three more Shazam answers (*Let It Roll*, *I Wanna* and an unrelated club mix) scored 48%
and were left out. The first two are in the full set, so a slightly lower bar for reels
would have found them.

The 31-second reel cannot be lined up with the original, because the pieces are too short
to match. So it is fingerprinted on its own, in windows every 5 s plus its last seconds:

```text
Tracklist:
00:00 Floorplan - Never Grow Old (Re-Plant) [Mixed]
00:18 Bella - Orchestra Spring

Links:
1. Floorplan - Never Grow Old (Re-Plant) [Mixed]: https://musicbrainz.org/recording/740ec554-8234-4f9a-a5d6-8d8eee254b28
2. Bella - Orchestra Spring: https://sallyc.bandcamp.com/track/orchestra-spring

Tracklist by setlister (https://github.com/dnk8n/setlister). ID = not identified yet; corrections welcome.
```

Shazam on 12-second excerpts by hand also finds *Bukom Mashie* at 0 s, which setlister
misses here. At 8 s it finds Aretha Franklin's *Never Grow Old*, the sample source of
Floorplan's *Never Grow Old (Re-plant)*. Reporting a recognised sample source as a hint for
the track that uses it would be a useful addition.

## Track notes: facts only vs Claude (Haiku)

Facts-only notes are built from MusicBrainz, Discogs and the file tags, with no model
involved. With `--llm-notes`, Haiku gets the same facts and is told to use nothing else.
The comparison below covers two versions of the prompt, because the first version's
weaknesses led to a change.

**First prompt** (commit 5ed5b8b). Haiku wrote a note for all 22 tracks:

| Track | Facts only | `claude-code/haiku` |
|---|---|---|
| Amy Douglas, Luke Solomon, Queen Rose - Light You Up | Released in 2017 on Classic Music Company. | Luke Solomon, Queen Rose, and Amy Douglas collaborated on "Light You Up," released by Classic Music Company in October 2017. The track appeared on Defected's Most Rated 2018 compilation. |
| Danny Wabbit - Internal Jungle | Released in 2021 on Tronic. | "Internal Jungle" is Danny Wabbit's November 2021 contribution to the All Stars 2022 compilation on Tronic. The track marked an appearance on the label for this artist. |
| Matt Darey & Lost Tribe - Gamemaster | Released in 1997 on Armada Music. | Gamemaster was originally produced by Matt Darey and Lost Tribe in 1996. The original mix is featured on Darey's 25-year retrospective, released by Armada Music in 2019. |
| Dan Fresco - Vanilla | Released in 2026. | Raz Fresco's "Vanilla Skies" appears on God Made Devil, released in 2018. |
| Shumba Youth / Zed Bias - London Town (4x4 VIP Refix) | Released in 2024. | No facts provided for this track. I need information about the artist, label, release context, or any other details to write an accurate liner note. Please share what's known about this release. |

- **Better when the facts are rich.** Haiku used release dates, compilations and label
  history from MusicBrainz to give context that the facts-only sentence leaves out (rows
  1–3).
- **Garbage in, garbage out.** For *Dan Fresco - Vanilla*, the MusicBrainz lookup matched
  the wrong recording (Raz Fresco's "Vanilla Skies"). Haiku faithfully described that wrong
  record. The facts-only note was just as wrong ("2026"), but less visibly so. The fix
  belongs in the lookup, which needs a stricter artist match, not in the prompt.
- **Thin facts lead to refusals or filler.** With no facts, Haiku wrote a refusal and
  setlister published it as the note (row 5). With almost no facts it padded instead: "The
  title suggests orchestral arrangements" for *Bella - Orchestra Spring*.

**Second prompt** (commit e7c9d8f). This version skips the model when there are no facts,
asks it to reply `NONE` when the facts are thin, and filters refusals. Haiku now wrote
only 2 of 22 notes (*Light You Up* and *Gamemaster*, both richer than before), and the other
20 fell back to the facts-only sentence. That removed the refusals and the invented
details, but it overcorrected: tracks with a label, a year and a Discogs release, such as
*Floorplan - Never Grow Old (Re-plant)*, also got `NONE`. The bar for "too thin" needs
loosening, e.g. a note is allowed whenever the facts include a label or a related release.

**Facts are not stable between runs.** The same track got different years from run to run:
*Deep Burnt* 2003 vs 2008, and *Yeke Yeke (Hardfloor Mix)* 2005 vs 2012. This happens
because the MusicBrainz lookup picks one of several matching recordings. Choosing the
earliest release, deterministically, would make both kinds of note consistent.

**Cost.** Through the Claude Code CLI, one call per track on the user's existing
subscription with no API key. That was about 6–7 extra minutes per set with the first
prompt, and about 3 minutes with the second.

## What this run taught us

1. **A full original recording does most of the work.** Matching the history files against
   the original placed 11 of 15 history tracks to the second, with no network use. Lining
   the recording up with the online copy then moves every timestamp onto each upload,
   cuts included.
2. **A short play is usually a false positive.** Before the short-play rule, the tracklist
   carried about 16 extra 20-second Shazam rows (Darude, 2 Unlimited, Tiësto…). They are now
   listed separately for checking instead of being published.
3. **Free recognisers need gentle use.** At one Shazam request per second the IP was
   blocked after about 25 requests. At one every 4 s, with back-off and an on-disk cache,
   the first full run took 10.6 minutes and every later run under 3 minutes.
4. **Confirmed links only.** Every link points to a page for that track or release, and
   there are no search URLs. On the full upload, across 22 tracks, that gave 15 YouTube,
   13 SoundCloud, 13 MusicBrainz, 12 Bandcamp and 2 Discogs links. Bandcamp only started
   working after its search endpoint replaced HTML scraping. Some SoundCloud matches are
   fan re-uploads rather than official pages, and Discogs exact matches are still rare.
5. **Highlight reels need both signals.** Lining a reel up with the original moves the
   original's evidence onto the reel. Fingerprinting the reel's own audio catches what the
   alignment misses. Each piece of a reel is short, so the short-play rule must not apply
   to reels. With both signals the 2-minute reel gets 3 of its tracks. The 31-second reel gets
   2 tracks, from its own audio only, using 5-second steps.
6. **Keys must be the right kind.** An AcoustID *user* key looks valid but is rejected for
   lookups. `doctor` now tests the key with one request.
