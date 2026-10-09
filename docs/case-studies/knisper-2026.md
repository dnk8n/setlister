# Case study: Pepper & Pumpernickl at Knisper 2026

A real back-to-back set, run end to end on a MacBook (Apple Silicon). It shows what
setlister finds with a full-length original recording and one DJ's rekordbox history,
against four online uploads of the same event.

> **Status: being filled in.** Sections marked TODO are written from the actual runs.
> Instructions for whoever fills them are at the bottom and are deleted afterwards.

## Inputs

| Input | How it was passed | Committed? |
|---|---|---|
| Original recording, 1h55m WAV (trimmed board recording) | `--original media/<recording>.WAV` | No. Audio never goes in the repo; `media/` is gitignored. |
| rekordbox history of one of the two DJs (`.txt` and `.m3u8`) | `-H media/<history>.txt -H media/<history>.m3u8` | No (personal library paths). |
| Online copies | the four URLs below | n/a |

Online copies: TODO list the four YouTube URLs with their titles and durations.

## Commands

TODO the exact commands (relative paths), first without and then with `--llm-notes`.

## Results per upload

TODO a table per URL: identified, `ID`, low-confidence rows left out, how the upload aligned
to the original (offset, cuts, speed), and run time. Then each `description.txt` block.

## Track notes: facts only vs Claude (Haiku)

TODO 4–5 tracks side by side: the facts-only note and the `claude-code/haiku` note, then a
few lines on accuracy, anything invented, and the extra run time.

## What this run taught us

TODO

<!--
Instructions for the session filling this in (delete this block when done):
1. Keep the no-LLM outputs of the 4 runs in out/_nollm/<set>/ (gitignored).
2. Set notes.model = "claude-code/haiku" in the local setlister.toml; `setlister doctor`
   must show the Claude Code check as OK (otherwise the user must run `claude` and /login).
3. Re-run the 4 URLs with the same inputs plus --llm-notes; notes are never cached.
4. Fill the TODOs from out/_nollm/ and out/. No absolute paths, usernames, keys or media.
   Commit only this file, on branch case-study-and-results, and push.
5. Do not change code; report anything that looks wrong instead.
-->
