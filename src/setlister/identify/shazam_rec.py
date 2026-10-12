"""Shazam via the community `shazamio` client.

Free and very robust to DJ mixing (tempo changes, overlaps, crowd noise), so it is usually
the most effective free recogniser for sets. It is NOT an official API: it may break or be
rate limited, and you are responsible for respecting Shazam's terms. On by default;
set `identify.shazam = false` to opt out.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from setlister.identify import RecognizerError
from setlister.models import Source, TrackRef


class ShazamRecognizer:
    name = Source.SHAZAM

    def available(self) -> tuple[bool, str]:
        try:
            import shazamio  # noqa: F401
        except ImportError:
            return False, "shazamio not installed (pip install shazamio)"
        return True, ""

    def recognize(self, wav: Path) -> list[tuple[TrackRef, float]]:
        from aiohttp_retry import ExponentialRetry
        from shazamio import HTTPClient, Shazam

        # shazamio's default retries a 429 up to 20 times with waits of up to a minute, which
        # looks like a hang. Retry server errors briefly and report rate limits instead.
        client = HTTPClient(
            retry_options=ExponentialRetry(attempts=2, max_timeout=5, statuses={500, 502, 503, 504})
        )

        async def go():
            shazam = Shazam(http_client=client)
            fn = getattr(shazam, "recognize", None) or shazam.recognize_song
            return await fn(str(wav))

        try:
            res = asyncio.run(go())
        except Exception as e:
            raise RecognizerError(type(e).__name__) from e
        if not isinstance(res, dict) or ("matches" not in res and "track" not in res):
            raise RecognizerError("unexpected response (rate limited?)")
        track = res.get("track")
        if not track:
            return []
        isrc = track.get("isrc")
        album = label = year = None
        for section in track.get("sections", []):
            for md in section.get("metadata", []) or []:
                k, v = md.get("title"), md.get("text")
                if k == "Album":
                    album = v
                elif k == "Label":
                    label = v
                elif k == "Released" and str(v)[:4].isdigit():
                    year = int(str(v)[:4])
        ref = TrackRef(
            artist=track.get("subtitle", ""),
            title=track.get("title", ""),
            isrc=isrc,
            album=album,
            label=label,
            year=year,
        )
        return [(ref, 0.8)]
