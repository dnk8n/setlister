"""The end-to-end run. Cheap sources first; heavy audio work only where still needed.

Stages
  1. text      description, chapters and comments of the online post (yt-dlp)
  2. history   DJ software histories + tags of the local files they point to
  3. audio     match local files against the recording; align original <-> online copy
  4. recognise fingerprint stretches nothing else explained (AcoustID, optional Shazam)
  5. resolve   merge all evidence into one setlist with confidence and contenders
  6. enrich    facts and links (MusicBrainz, Discogs, Bandcamp, SoundCloud, YouTube), notes
  7. write     out/<set>/
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from setlister.audio.matcher import CLIP_SECONDS
from setlister.config import Config
from setlister.models import Entry, Evidence, Setlist, Source, TrackRef
from setlister.progress import track
from setlister.resolve import pick_in_order, resolve, same_track
from setlister.timefmt import format_timestamp

log = logging.getLogger(__name__)
console = Console(stderr=True)


@dataclass
class RunInputs:
    url: str | None = None
    original: Path | None = None  # the DJ's own recording (may be longer than the online copy)
    online_audio: Path | None = None  # local copy of the online audio (skips the download)
    histories: list[Path] = field(default_factory=list)
    offline: bool = False  # no network lookups at all
    title: str | None = None


def step(msg: str) -> None:
    console.print(f"[bold cyan]›[/] {msg}")


def run(inputs: RunInputs, cfg: Config) -> tuple[Setlist, Path]:
    key = _set_key(inputs)
    cache = cfg.cache_dir / key
    cache.mkdir(parents=True, exist_ok=True)
    evidence: list[Evidence] = []

    # 1. text -------------------------------------------------------------------------------
    info: dict = {}
    if inputs.url and not inputs.offline:
        from setlister.sources import youtube

        step("Reading the online post (title, description, chapters, comments)")
        info = youtube.fetch_info(
            inputs.url,
            cache,
            comments=cfg.sources.youtube_comments,
            max_comments=cfg.sources.max_comments,
        )
        evidence += text_evidence(info)
        console.print(f"  found {len(evidence)} timestamped tracks in text")
    duration = info.get("duration")

    # 2. history ----------------------------------------------------------------------------
    history: list[TrackRef] = []
    if inputs.histories:
        from setlister.sources import rekordbox

        history = rekordbox.load_histories(inputs.histories)
        for i, t in enumerate(history):
            if t.path and Path(t.path).is_file():
                history[i] = rekordbox.enrich_from_tags(t, rekordbox.read_tags(Path(t.path)))
        playable = sum(1 for t in history if t.path and Path(t.path).is_file())
        step(f"History: {len(history)} tracks, {playable} local files available")

    # 3. audio ------------------------------------------------------------------------------
    recording, online_path, segments = _audio_inputs(inputs, info, cfg, cache)
    offset_note = None
    if recording:
        from setlister.audio.features import features_for
        from setlister.audio.matcher import (
            CLIP_SECONDS,
            MixIndex,
            align,
            align_clip,
            locate_candidates,
            original_span_to_online,
            original_to_online,
        )

        step(f"Analysing {recording.name}")
        rec_feat = features_for(recording, cfg.audio.analysis_sr, cfg.cache_dir)
        index = MixIndex(rec_feat)
        duration = duration or rec_feat.duration
        if inputs.original and online_path and online_path != recording:
            step("Aligning your original recording with the online copy")
            on_feat = features_for(online_path, cfg.audio.analysis_sr, cfg.cache_dir)
            is_clip = on_feat.duration < CLIP_SECONDS
            segments = align_clip(index, on_feat) if is_clip else align(index, on_feat)
            offset_note = describe_alignment(segments, rec_feat.duration, on_feat.duration)
            duration = on_feat.duration
            if not segments:
                # Fall back to analysing the online copy itself, so times are still right.
                offset_note += " Analysed the online copy directly instead."
                recording, rec_feat = online_path, on_feat
                index = MixIndex(rec_feat)
            console.print(f"  {offset_note}")
        elif inputs.original and info.get("duration"):
            offset_note = (
                "The online copy is as long as the original recording, so they were "
                "assumed identical (no download)."
            )

        # A clip's pieces are seconds long, so don't stretch them; a full set gets slack for
        # tracks that began just before a cut.
        slack = 0.0 if segments and on_feat.duration < CLIP_SECONDS else 60.0

        def to_online(t: float) -> float | None:
            return original_to_online(t, segments, slack) if segments else t

        def spans(s: float, e: float) -> list[tuple[float, float]]:
            if not segments:
                return [(s, e)]
            return original_span_to_online(s, e, segments) or (
                [(a, b)] if (a := to_online(s)) is not None and (b := to_online(e)) else []
            )

        files = [(i, t) for i, t in enumerate(history) if t.path and Path(t.path).is_file()]
        if files:
            step(f"Locating {len(files)} history tracks in the recording")
            options: list[list[Evidence]] = [[] for _ in history]
            more_pieces: dict[int, list[Evidence]] = {}  # a clip can show a track several times
            for i, t in track(files, "Locating", console, lambda f: f[1].display):
                feat = features_for(Path(t.path), cfg.audio.analysis_sr, cfg.cache_dir)
                for m in locate_candidates(index, feat, max_rate_change=cfg.audio.max_tempo_change)[
                    :3
                ]:
                    pieces = [
                        Evidence(
                            track=t,
                            source=Source.LOCAL_MATCH,
                            confidence=m.confidence,
                            start=s,
                            end=e,
                            order=i,
                            detail=f"rate {m.rate:.3f}",
                        )
                        for s, e in spans(m.start, m.end)
                    ]
                    if pieces:
                        options[i].append(pieces[0])
                        more_pieces[id(pieces[0])] = pieces[1:]
            chosen = pick_in_order(options)
            if slack == 0.0:  # a clip: placements rest on seconds of audio, so weigh them less
                for c in chosen:
                    c.confidence = round(c.confidence * 0.7, 3)
                    for p in more_pieces.get(id(c), []):
                        p.confidence = c.confidence
            evidence += chosen
            evidence += [p for c in chosen for p in more_pieces.get(id(c), [])]
            console.print(f"  placed {len(chosen)} of {len(files)}")

        # 4. recognise ----------------------------------------------------------------------
        if not inputs.offline:
            clip_ranges = (
                [
                    (s.online_start * s.rate + s.offset, s.online_end * s.rate + s.offset)
                    for s in segments
                ]
                if segments and slack == 0.0
                else None
            )
            evidence += recognise_gaps(
                recording, rec_feat.duration, evidence, cfg, to_online, clip_ranges
            )
            if clip_ranges and online_path:
                # Also listen to the clip itself: a direct match beats one carried over from
                # the original through a few seconds of alignment.
                evidence += recognise_gaps(online_path, on_feat.duration, [], cfg, lambda t: t)

    # History tracks we couldn't place still count as "played, time unknown".
    placed = {e.order for e in evidence if e.source == Source.LOCAL_MATCH}
    unplaced = [t for i, t in enumerate(history) if i not in placed]

    # 5. resolve ----------------------------------------------------------------------------
    step("Resolving evidence into a setlist")
    rejected: list[Entry] = []
    entries = resolve(
        evidence,
        duration=duration,
        max_contenders=cfg.identify.max_contenders,
        min_confidence=cfg.output.min_confidence_to_name,
        rejected=rejected,
        clip=bool(duration and duration < CLIP_SECONDS),
    )
    suggest_from_history(entries, evidence, history, unplaced, cfg.identify.max_contenders)

    if duration and duration < 300:
        console.print(
            f"  [yellow]This upload is only {format_timestamp(duration)} long, so it is probably "
            "a clip or highlight reel rather than the set; only what is audible in it can be "
            "identified.[/]"
        )
    if not any(not e.is_unknown for e in entries):
        console.print("  [yellow]No tracks could be identified in this upload.[/]")

    # 6. enrich -----------------------------------------------------------------------------
    if not inputs.offline:
        step("Finding links and writing track notes")
        named = [e for e in entries if not e.is_unknown]
        how = f"notes: {cfg.notes.model}" if cfg.notes.llm else "notes: facts only"
        step(f"{len(named)} tracks ({how})")
        for e in track(named, "Links & notes", console, lambda e: e.track.display):
            enrich(e, cfg)

    sl = Setlist(
        url=inputs.url or str(inputs.original or ""),
        title=inputs.title or info.get("title", ""),
        duration=duration,
        entries=entries,
        offset_note=offset_note,
        rejected=rejected,
    )
    named = [e.track for e in entries if not e.is_unknown]
    unplaced = [t for t in unplaced if not any(same_track(t, n) for n in named)]
    if unplaced and not (duration and duration < CLIP_SECONDS):  # a clip skips most tracks
        sl.offset_note = (
            (sl.offset_note or "") + " Also in the DJ history but not heard in this "
            "recording: " + "; ".join(t.display for t in unplaced) + "."
        ).strip()

    # 7. write ------------------------------------------------------------------------------
    from setlister.output import folder_name, write_all

    outdir = write_all(
        sl,
        cfg.output.directory / folder_name(sl.title or key, info.get("id")),
        cfg.output.min_confidence_to_name,
        sites=cfg.links.sites,
    )
    return sl, outdir


def suggest_from_history(
    entries: list[Entry],
    evidence: list[Evidence],
    history: list[TrackRef],
    unplaced: list[TrackRef],
    max_contenders: int,
) -> None:
    """An unexplained gap between two placed history tracks was probably filled by the
    unplaced history tracks that sit between them in play order: offer those as contenders."""
    if not unplaced:
        return
    order_of = {id(t): i for i, t in enumerate(history)}
    placed = sorted(
        (e.start, e.order)
        for e in evidence
        if e.source == Source.LOCAL_MATCH and e.order is not None
    )
    for entry in entries:
        if not entry.is_unknown:
            continue
        before = max((o for st, o in placed if st <= entry.start), default=-1)
        after = min(
            (o for st, o in placed if st >= (entry.end or entry.start)), default=len(history)
        )
        for t in unplaced:
            if before < order_of[id(t)] < after and len(entry.contenders) < max_contenders:
                entry.contenders.append(t)


def _set_key(inputs: RunInputs) -> str:
    import hashlib

    basis = inputs.url or str(inputs.original or inputs.online_audio)
    return hashlib.sha1(basis.encode()).hexdigest()[:12]


def text_evidence(info: dict) -> list[Evidence]:
    from setlister.sources.tracklist_text import chapters_to_tracks, parse_timestamped

    def ev(tracks, source, conf):
        out = []
        for i, t in enumerate(tracks):
            nxt = tracks[i + 1].time if i + 1 < len(tracks) else info.get("duration")
            out.append(
                Evidence(
                    track=TrackRef(artist=t.artist, title=t.title),
                    source=source,
                    confidence=conf,
                    start=t.time,
                    end=nxt,
                    detail=t.line,
                )
            )
        return out

    found = ev(parse_timestamped(info.get("description") or ""), Source.DESCRIPTION, 0.9)
    chapters = chapters_to_tracks(info.get("chapters") or [])
    if len(chapters) >= 3:
        found += ev(chapters, Source.CHAPTERS, 0.85)
    best: list = []
    best_score = 0.0
    for c in info.get("comments") or []:
        tracks = parse_timestamped(c.get("text", ""))
        score = len(tracks) * (2 if c.get("is_uploader") else 1) + min(c.get("likes", 0), 50) / 10
        if tracks and score > best_score:
            best, best_score = tracks, score
            best_is_uploader = c.get("is_uploader")
    if best:
        found += ev(best, Source.COMMENT, 0.85 if best_is_uploader else 0.7)
    return found


def _audio_inputs(inputs: RunInputs, info: dict, cfg: Config, cache: Path):
    """Decide which audio to analyse, downloading the online copy only when it's needed."""
    online = inputs.online_audio
    if inputs.original:
        need_online = cfg.audio.download_when_original_given
        if info.get("duration") and not online:
            from setlister.audio.features import decode  # noqa: F401  (ffmpeg present)

            orig_dur = _probe_duration(inputs.original)
            if orig_dur and abs(orig_dur - info["duration"]) > 2:
                need_online = True  # the online copy was trimmed or cut: we must align
        if need_online and not online and inputs.url and not inputs.offline:
            from setlister.sources import youtube

            step("Online copy differs from your original: downloading its audio to align")
            online = youtube.download_audio(inputs.url, cache)
        return inputs.original, online, []
    if online:
        return online, online, []
    if (
        inputs.url
        and not inputs.offline
        and (inputs.histories or cfg.identify.acoustid or cfg.identify.shazam)
    ):
        from setlister.sources import youtube

        step("Downloading the online audio (audio only)")
        p = youtube.download_audio(inputs.url, cache)
        return p, p, []
    return None, None, []


def _probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None


def describe_alignment(segments, original_duration: float, online_duration: float) -> str:
    if not segments:
        return "Could not line up the online copy with the original recording."
    first = segments[0]
    parts = []
    if abs(first.offset) >= 1:
        if first.offset > 0:
            parts.append(
                f"The online copy starts {format_timestamp(first.offset)} into the original recording"
            )
        else:
            parts.append(
                f"The online copy has {format_timestamp(-first.offset)} extra at the start"
            )
    if abs(first.rate - 1) > 0.001:
        faster = "faster" if first.rate > 1 else "slower"
        parts.append(f"plays {abs(first.rate - 1):.1%} {faster} than the original")
    if len(segments) > 1:
        parts.append(f"and has {len(segments) - 1} cut(s)")
    if not parts:
        parts.append("The online copy lines up with the original recording")
    return (
        " ".join(parts)
        + f" (online {format_timestamp(online_duration)}, original {format_timestamp(original_duration)})."
    )


CLIP_WINDOW, CLIP_STEP = 12.0, 10.0  # highlight reels cut every few seconds


def recognise_gaps(
    recording: Path,
    rec_duration: float,
    evidence: list[Evidence],
    cfg: Config,
    to_online,
    clip_ranges: list[tuple[float, float]] | None = None,
) -> list[Evidence]:
    """Fingerprint the stretches no other evidence explains. `clip_ranges` (times in the
    recording) limits this to the pieces a short clip was cut from."""
    from setlister.identify import CachedRecognizer, recognizers

    usable = []
    for r in recognizers(cfg):
        ok, why = r.available()
        if ok:
            pace = cfg.identify.shazam_pace_seconds if r.name == Source.SHAZAM else 0.0
            usable.append(
                CachedRecognizer(
                    r,
                    cfg.cache_dir,
                    pace_seconds=pace,
                    on_wait=lambda s, why, n=r.name.value: console.print(
                        f"  [yellow]{n} failed ({why}); waiting {s:.0f} s before retrying[/]"
                    ),
                )
            )
        else:
            console.print(f"  [yellow]skipping {r.name.value}[/]: {why}")
    if not usable:
        return []
    covered = [
        (e.start, e.end)
        for e in evidence
        if e.start is not None and e.end is not None and e.confidence >= 0.5
    ]
    win, step_s = cfg.identify.window_seconds, cfg.identify.step_seconds
    starts = [15.0]  # skip the intro/crowd noise at the very start of a set...
    ends = [rec_duration]
    if clip_ranges:
        win, step_s = CLIP_WINDOW, CLIP_STEP
        starts, ends = [a for a, _ in clip_ranges], [b for _, b in clip_ranges]
    elif rec_duration < CLIP_SECONDS:  # ...unless it's a short clip: then check all of it
        win = min(CLIP_WINDOW, rec_duration)
        # Very short reels change track every few seconds: overlap the windows more.
        step_s = CLIP_STEP if rec_duration >= 60 else CLIP_STEP / 2
        starts = [0.0]
    times = []
    for t, end in zip(starts, ends, strict=True):
        # A clip's pieces may be shorter than a window: still look once at each. (Reading past
        # a piece's end is fine: it is the recording's own continuous audio.)
        while (t < end) if clip_ranges else (t + win <= end):
            on = to_online(t)
            if on is not None and not any(s - 10 <= on <= e - 10 for s, e in covered):
                times.append(t)
            t += step_s
    if rec_duration < CLIP_SECONDS and not clip_ranges and rec_duration - win not in times:
        times.append(max(0.0, rec_duration - win))  # the clip's last seconds too
    if not times:
        return []
    step(
        f"Fingerprinting {len(times)} uncovered moments with {', '.join(r.name.value for r in usable)}"
    )
    hits: list[tuple[float, TrackRef, float, Source]] = []
    with tempfile.TemporaryDirectory() as tmp:
        for t in track(times, "Fingerprinting", console, lambda t: "at " + format_timestamp(t)):
            wav = Path(tmp) / "w.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{t:.2f}",
                    "-t",
                    f"{win:.2f}",
                    "-i",
                    str(recording),
                    "-ac",
                    "2",
                    "-ar",
                    "44100",
                    str(wav),
                ],
                check=True,
            )
            for r in usable:
                if r.gave_up:
                    continue
                found = r.recognize(wav)
                if r.gave_up:
                    console.print(
                        f"  [yellow]{r.name.value} skipped for the rest of this run: "
                        f"{r.reason}. Answers so far are cached.[/]"
                    )
                for ref, score in found[:2]:
                    on = to_online(t)
                    if on is not None:
                        hits.append((on, ref, score, r.name))
    for r in usable:
        console.print(f"  {r.summary()}", highlight=False)
    return group_hits(hits, win)


def group_hits(hits, window: float) -> list[Evidence]:
    """Consecutive windows naming the same track become one piece of evidence."""
    from setlister.resolve import combine, same_track

    hits.sort(key=lambda h: h[0])
    groups: list[Evidence] = []
    for t, ref, score, src in hits:
        g = next(
            (
                g
                for g in reversed(groups[-4:])
                if same_track(g.track, ref) and t - (g.end or g.start) < 120
            ),
            None,
        )
        if g:
            g.end = t + window
            g.confidence = combine(g.confidence, score * 0.6)
        else:
            groups.append(
                Evidence(
                    track=ref, source=src, confidence=round(score * 0.6, 3), start=t, end=t + window
                )
            )
    return groups


def enrich(entry: Entry, cfg: Config) -> None:
    from setlister.identify import musicbrainz
    from setlister.links import discogs, find_links
    from setlister.notes import write_note

    facts: dict = {}
    known = []
    rec = musicbrainz.find_recording(entry.track)
    if rec:
        f, known = musicbrainz.facts_and_links(rec)
        facts.update(f)
        entry.note_sources.append("MusicBrainz")
    links = find_links(
        entry.track,
        cfg.links.sites,
        resolve_exact=cfg.links.resolve_exact,
        known=known,
        discogs_release_id=entry.track.discogs_release_id,
    )
    known_sites = {link.site for link in links}
    extra = [
        k for k in known if k.site not in known_sites and k.site in ("musicbrainz", "beatport")
    ]
    entry.links = links + extra
    dlink = next((link for link in links if link.site == "discogs" and link.exact), None)
    if dlink:
        try:
            facts.update(discogs.facts(dlink.url))
            entry.note_sources.append("Discogs")
        except Exception as e:
            log.debug("discogs facts: %s", e)
    if entry.track.label:
        facts.setdefault("label_from_file_tags", entry.track.label)
    entry.note, how = write_note(entry.track, facts, cfg.notes)
    if how not in ("facts", "disabled"):
        entry.note_sources.append(f"written by {how}")
