"""AcoustID (free, open fingerprint database run by the MusicBrainz community).

Needs `fpcalc` (Chromaprint) on PATH and a free application key. Works best on long, clean
excerpts at original speed, so it's a weaker tool for DJ mixes than for whole tracks, but
it's free and open.
"""

from __future__ import annotations

import shutil
from pathlib import Path

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

        key = get_secret("acoustid_key")
        out = []
        try:
            for score, rid, title, artist in acoustid.match(key, str(wav)):
                if title:
                    out.append(
                        (
                            TrackRef(
                                artist=artist or "", title=title, musicbrainz_recording_id=rid
                            ),
                            float(score),
                        )
                    )
        except acoustid.AcoustidError:
            return []
        return out
