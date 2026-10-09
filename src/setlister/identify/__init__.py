"""Audio recognisers for stretches of the set that no cheap source explained.

Each recogniser takes a short WAV excerpt and returns candidate tracks with a score in 0..1.
Add a new one (e.g. a paid service) by implementing `Recognizer` and registering it in
`recognizers()`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Protocol

from setlister.models import Source, TrackRef

log = logging.getLogger(__name__)


class RecognizerError(Exception):
    """The service did not answer properly (rate limited, down, bad response). Unlike an
    empty result, this is not cached and counts towards giving up on the service."""


class Recognizer(Protocol):
    name: Source

    def available(self) -> tuple[bool, str]:
        """(usable, reason if not)."""

    def recognize(self, wav: Path) -> list[tuple[TrackRef, float]]:
        """Matches for the excerpt (empty if none). Raises RecognizerError on failure."""


class CachedRecognizer:
    """Remembers every answer on disk, keyed by the excerpt's bytes, so a re-run never asks a
    service the same question twice. After `give_up_after` failures in a row the service is
    skipped for the rest of the run instead of slowing it down."""

    def __init__(self, inner: Recognizer, cache_dir: Path, give_up_after: int = 3):
        self.inner, self.name = inner, inner.name
        self.dir = cache_dir / "recognitions" / inner.name.value
        self.give_up_after = give_up_after
        self.failures_in_a_row = 0
        self.asked = self.cached = self.failed = 0
        self.gave_up = False

    def available(self) -> tuple[bool, str]:
        return self.inner.available()

    def recognize(self, wav: Path) -> list[tuple[TrackRef, float]]:
        path = self.dir / (hashlib.sha1(wav.read_bytes()).hexdigest() + ".json")
        if path.exists():
            self.cached += 1
            return [(TrackRef(**r), s) for r, s in json.loads(path.read_text())]
        if self.gave_up:
            return []
        self.asked += 1
        try:
            found = self.inner.recognize(wav)
        except RecognizerError as e:
            self.failed += 1
            self.failures_in_a_row += 1
            log.info("%s failed: %s", self.name.value, e)
            if self.failures_in_a_row >= self.give_up_after:
                self.gave_up = True
            return []
        self.failures_in_a_row = 0
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([(r.model_dump(exclude_none=True), s) for r, s in found]))
        return found

    def summary(self) -> str:
        s = f"{self.name.value}: {self.asked} asked, {self.cached} from cache"
        if self.failed:
            s += f", {self.failed} failed"
        if self.gave_up:
            s += ", gave up after repeated failures (probably rate limited; try again later)"
        return s


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
