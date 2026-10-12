"""Audio recognisers for stretches of the set that no cheap source explained.

Each recogniser takes a short WAV excerpt and returns candidate tracks with a score in 0..1.
Add a new one (e.g. a paid service) by implementing `Recognizer` and registering it in
`recognizers()`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Protocol

from setlister.models import Source, TrackRef

log = logging.getLogger(__name__)


class RecognizerError(Exception):
    """The service did not answer properly (rate limited, down, bad response). Unlike an
    empty result, this is not cached and counts towards giving up on the service."""


class PermanentRecognizerError(RecognizerError):
    """Retrying cannot help (e.g. the key was rejected): stop using the service at once."""


class Recognizer(Protocol):
    name: Source

    def available(self) -> tuple[bool, str]:
        """(usable, reason if not)."""

    def recognize(self, wav: Path) -> list[tuple[TrackRef, float]]:
        """Matches for the excerpt (empty if none). Raises RecognizerError on failure."""


class CachedRecognizer:
    """Remembers every answer on disk (matches and "no match" alike), keyed by the excerpt's
    bytes, so a re-run never asks a service the same question twice.

    When the service fails (rate limit, outage) it waits and tries again, with each wait in
    `backoff` longer than the last; once those are used up the service is skipped for the
    rest of the run. A rejected key stops it at once."""

    def __init__(
        self,
        inner: Recognizer,
        cache_dir: Path,
        *,
        pace_seconds: float = 0.0,
        backoff: tuple[float, ...] = (60.0, 180.0),
        on_wait=None,
    ):
        self.inner, self.name = inner, inner.name
        self.dir = cache_dir / "recognitions" / inner.name.value
        self.pace, self.backoff = pace_seconds, backoff
        self.on_wait = on_wait or (lambda seconds, why: None)
        self._last_call = 0.0
        self.asked = self.cached = self.failed = 0
        self.gave_up = False
        self.reason = ""

    def available(self) -> tuple[bool, str]:
        return self.inner.available()

    def recognize(self, wav: Path) -> list[tuple[TrackRef, float]]:
        path = self.dir / (hashlib.sha1(wav.read_bytes()).hexdigest() + ".json")
        if path.exists():
            self.cached += 1
            return [(TrackRef(**r), s) for r, s in json.loads(path.read_text())]
        if self.gave_up:
            return []
        for wait in (*self.backoff, None):
            found = self._ask(wav)
            if found is not None:
                self.dir.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps([(r.model_dump(exclude_none=True), s) for r, s in found])
                )
                return found
            if self.gave_up:
                return []
            if wait is None:
                break
            self.on_wait(wait, self.reason)
            time.sleep(wait)
        self.gave_up = True
        self.reason = f"still failing after backing off ({self.reason}); try again later"
        return []

    def _ask(self, wav: Path) -> list[tuple[TrackRef, float]] | None:
        delay = self._last_call + self.pace - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last_call = time.monotonic()
        self.asked += 1
        try:
            return self.inner.recognize(wav)
        except PermanentRecognizerError as e:
            self.failed += 1
            self.gave_up, self.reason = True, str(e)
        except RecognizerError as e:
            self.failed += 1
            self.reason = str(e)
            log.info("%s failed: %s", self.name.value, e)
        return None

    def summary(self) -> str:
        s = f"{self.name.value}: {self.asked} asked, {self.cached} from cache"
        if self.failed:
            s += f", {self.failed} failed"
        if self.gave_up:
            s += f", stopped: {self.reason}"
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
