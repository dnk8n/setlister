"""Data model shared by every stage of the pipeline.

Each information source produces `Evidence`: "track X is (probably) playing around time T".
The resolver turns evidence into `Entry` rows of a `Setlist`.
All times are seconds relative to the *online* version of the set.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class TrackRef(BaseModel):
    artist: str = ""
    title: str = ""
    album: str | None = None
    label: str | None = None
    year: int | None = None
    bpm: float | None = None
    key: str | None = None
    duration: float | None = None
    # Local file (e.g. from a rekordbox history). Never written to output: it reveals the
    # DJ's own folders, and setlist.json may be shared.
    path: str | None = Field(default=None, exclude=True)
    musicbrainz_recording_id: str | None = None
    isrc: str | None = None
    discogs_release_id: str | None = None

    @model_validator(mode="after")
    def _tidy(self) -> TrackRef:
        from setlister.textnorm import tidy_artist_title

        self.artist, self.title = tidy_artist_title(self.artist, self.title)
        return self

    @property
    def display(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        return self.title or self.artist or "ID"

    def key_tuple(self) -> tuple[str, str]:
        from setlister.textnorm import norm

        return norm(self.artist), norm(self.title)


class Source(StrEnum):
    DESCRIPTION = "description"  # tracklist in the video description
    CHAPTERS = "chapters"  # YouTube chapters
    COMMENT = "comment"  # tracklist posted in comments
    HISTORY = "history"  # DJ software play history (order only, no times)
    LOCAL_MATCH = "local_match"  # local audio file matched against the recording
    ACOUSTID = "acoustid"
    SHAZAM = "shazam"
    ORIGINAL_SET = "original_set"  # the full set's tracklist, for a reel cut from it
    MANUAL = "manual"


class Evidence(BaseModel):
    track: TrackRef
    source: Source
    confidence: float = Field(ge=0.0, le=1.0)
    start: float | None = None
    end: float | None = None
    order: int | None = None  # position in a list that has no times (e.g. history)
    detail: str = ""


class Link(BaseModel):
    site: str  # bandcamp | discogs | soundcloud | youtube | musicbrainz | beatport ...
    url: str
    exact: bool = False  # False = a search URL, True = a page for this exact track/release


class Sample(BaseModel):
    """Material this track samples. `source` says how we know: "MusicBrainz" (a curated
    relation) or "heard in the mix" (a recogniser named it inside this track's stretch)."""

    track: TrackRef
    source: str


class Entry(BaseModel):
    start: float
    end: float | None = None
    track: TrackRef
    confidence: float
    sources: list[Source] = []
    contenders: list[TrackRef] = []  # alternatives when unsure
    samples: list[Sample] = []
    links: list[Link] = []
    note: str | None = None
    note_sources: list[str] = []

    @property
    def is_unknown(self) -> bool:
        return not (self.track.artist or self.track.title)


class Setlist(BaseModel):
    url: str
    title: str = ""
    duration: float | None = None
    entries: list[Entry] = []
    rejected: list[Entry] = []  # detections too weak for the list (shown separately)
    offset_note: str | None = None  # how the online version maps onto the original
    generated_by: str = "setlister"
