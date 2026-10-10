"""AcoustID (free, open fingerprint database run by the MusicBrainz community).

Needs `fpcalc` (Chromaprint) on PATH and a free application key. Works best on long, clean
excerpts at original speed, so it's a weaker tool for DJ mixes than for whole tracks, but
it's free and open.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from setlister.identify import PermanentRecognizerError, RecognizerError
from setlister.models import Source, TrackRef
from setlister.secrets import get_secret


class AcoustIDRecognizer:
    name = Source.ACOUSTID

    def available(self) -> tuple[bool, str]:
        if not shutil.which("fpcalc"):
            return False, "fpcalc not found (macOS: brew install chromaprint)"
        if not get_secret("acoustid_key"):
            return False, "no AcoustID key (free: https://acoustid.org/new-application)"
        return True, ""

    def recognize(self, wav: Path) -> list[tuple[TrackRef, float]]:
        import acoustid

        duration, fp = acoustid.fingerprint_file(str(wav))
        try:
            resp = acoustid.lookup(get_secret("acoustid_key"), fp, duration, meta=["recordings"])
        except acoustid.WebServiceError as e:
            raise RecognizerError(str(e)) from e
        check_response(resp)
        return [
            (TrackRef(artist=artist or "", title=title, musicbrainz_recording_id=rid), float(score))
            for score, rid, title, artist in acoustid.parse_lookup_result(resp)
            if title
        ]


INVALID_KEY = 4  # AcoustID error code for a rejected client key


def check_response(resp: dict) -> None:
    if resp.get("status") == "ok":
        return
    err = resp.get("error") or {}
    if err.get("code") == INVALID_KEY:
        raise PermanentRecognizerError(KEY_HELP)
    raise RecognizerError(err.get("message") or "unexpected response")


KEY_HELP = (
    "AcoustID rejected the key. Lookups need an application key "
    "(https://acoustid.org/new-application), not your user key; "
    "then run: setlister config set acoustid_key"
)


def key_problem(key: str) -> str | None:
    """One cheap request with a dummy fingerprint: a good key gets a fingerprint error,
    a bad one gets 'invalid API key'. None if the key looks fine or AcoustID is unreachable."""
    import acoustid

    try:
        resp = acoustid.lookup(key, "AQAAAA", 30)
    except acoustid.WebServiceError:
        return None
    err = (resp or {}).get("error") or {}
    return KEY_HELP if err.get("code") == INVALID_KEY else None
