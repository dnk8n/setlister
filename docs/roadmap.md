# Roadmap

Good first issues are marked ★.

- [ ] Paid recognisers, opt-in by config + keychain secret: AudD, ACRCloud.
- [ ] ★ 1001tracklists lookup (often has the answer; scraping is fragile and needs care with
      their terms).
- [ ] ★ Mixcloud: read an existing tracklist when present.
- [ ] rekordbox `master.db` via [pyrekordbox](https://github.com/dylanljones/pyrekordbox):
      history entries carry play timestamps, which would narrow the audio search further.
- [ ] Serato / Traktor / Engine DJ history importers.
- [ ] Optional neural transition detection on GPU / Apple Neural Engine for sets with no
      history and sparse fingerprints (only where cheap evidence left gaps).
- [ ] Sample-source detection for edits (e.g. WhoSampled lookup by identified track).
- [ ] `--from-json` to regenerate outputs after hand corrections.
- [ ] Support beyond macOS as a first-class target (Linux mostly works already; CI runs it).
