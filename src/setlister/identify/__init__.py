"""Audio recognisers for stretches of the set that no cheap source explained.

Each recogniser takes a short WAV excerpt and returns candidate tracks with a score in 0..1.
Add a new one (e.g. a paid service) by implementing `Recognizer` and registering it in
`recognizers()`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from setlister.models import Source, TrackRef


class Recognizer(Protocol):
    name: Source

    def available(self) -> tuple[bool, str]:
        """(usable, reason if not)."""

    def recognize(self, wav: Path) -> list[tuple[TrackRef, float]]: ...


def recognizers(cfg) -> list[Recognizer]:
    from setlister.identify.acoustid_rec import AcoustIDRecognizer
    from setlister.identify.shazam_rec import ShazamRecognizer

    out: list[Recognizer] = []
    if cfg.identify.shazam:
        out.append(ShazamRecognizer())
    if cfg.identify.acoustid:
        out.append(AcoustIDRecognizer())
    # TODO(paid): AudD and ACRCloud recognisers, enabled by config + keychain secret.
    return out
