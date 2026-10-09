"""Parsing and formatting of set timestamps."""

from __future__ import annotations

import re

_TS = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.\d+)?$")


def parse_timestamp(text: str) -> float:
    """'1:02:03' -> 3723.0, '02:03' -> 123.0."""
    m = _TS.match(text.strip())
    if not m:
        raise ValueError(f"not a timestamp: {text!r}")
    h, mnt, s = m.groups()
    return int(h or 0) * 3600 + int(mnt) * 60 + int(s)


def format_timestamp(seconds: float, *, force_hours: bool = False) -> str:
    """Format like YouTube chapters: M:SS, or H:MM:SS when needed."""
    total = max(0, int(round(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h or force_hours:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
