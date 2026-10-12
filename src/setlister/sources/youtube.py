"""Online set metadata and audio via yt-dlp (works for YouTube, SoundCloud, Mixcloud and
~1800 other sites, so nothing here is YouTube-specific despite the name)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def _ydl(opts: dict):
    import yt_dlp

    base = {"quiet": True, "no_warnings": True, "noprogress": True}
    return yt_dlp.YoutubeDL(base | opts)


def fetch_info(
    url: str, cache_dir: Path, *, comments: bool = True, max_comments: int = 300
) -> dict:
    """Title, description, duration, chapters and (optionally) top comments. Cached."""
    cache = cache_dir / "info.json"
    if cache.exists():
        return json.loads(cache.read_text())
    opts: dict = {"skip_download": True}
    if comments:
        opts["getcomments"] = True
        opts["extractor_args"] = {
            "youtube": {"comment_sort": ["top"], "max_comments": [str(max_comments), "all", "0"]}
        }
    with _ydl(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    keep = {
        k: info.get(k)
        for k in (
            "id",
            "title",
            "description",
            "duration",
            "chapters",
            "uploader",
            "webpage_url",
            "upload_date",
            "extractor_key",
        )
    }
    keep["comments"] = [
        {
            "text": c.get("text", ""),
            "author": c.get("author"),
            "likes": c.get("like_count") or 0,
            "is_uploader": bool(c.get("author_is_uploader")),
        }
        for c in (info.get("comments") or [])
    ]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(keep, ensure_ascii=False, indent=1))
    return keep


def download_audio(url: str, cache_dir: Path) -> Path:
    """Best audio-only stream (no video, no re-encode). Cached."""
    existing = sorted(cache_dir.glob("audio.*"))
    if existing:
        return existing[0]
    cache_dir.mkdir(parents=True, exist_ok=True)
    opts = {"format": "bestaudio/best", "outtmpl": str(cache_dir / "audio.%(ext)s")}
    with _ydl(opts) as ydl:
        ydl.extract_info(url, download=True)
    return sorted(cache_dir.glob("audio.*"))[0]


def search(query: str, site: str = "youtube", n: int = 5) -> list[dict]:
    """Top `n` search hits on YouTube ('ytsearchN') or SoundCloud ('scsearchN'), metadata only."""
    prefix = {"youtube": "ytsearch", "soundcloud": "scsearch"}[site]
    try:
        with _ydl({"skip_download": True, "extract_flat": True}) as ydl:
            res = ydl.extract_info(f"{prefix}{n}:{query}", download=False)
    except Exception as e:  # network / extractor errors shouldn't kill a run
        log.debug("search failed on %s: %s", site, e)
        return []
    return [h for h in res.get("entries") or [] if h]
