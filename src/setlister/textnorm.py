"""Lenient text normalisation for comparing artist/title strings from different sources."""

from __future__ import annotations

import re
import unicodedata

_FEAT = re.compile(r"\b(feat\.?|ft\.?|featuring)\b.*", re.I)
_PUNCT = re.compile(r"[^\w\s]")


def norm(text: str | None, *, drop_feat: bool = False) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("&", " and ").replace("’", "'")
    if drop_feat:
        t = _FEAT.sub("", t)
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


def similarity(a: str, b: str) -> float:
    """Token-set similarity in [0, 1], tolerant to word order and extra words."""
    from difflib import SequenceMatcher

    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    jacc = len(ta & tb) / len(ta | tb)
    seq = SequenceMatcher(None, na, nb).ratio()
    return max(jacc, seq)


def split_artist_title(line: str) -> tuple[str, str]:
    """'Artist - Title' -> ('Artist', 'Title'), splitting at the first separator.
    Falls back to ('', line)."""
    hits = [(line.find(sep), sep) for sep in (" - ", " – ", " — ", " -- ") if sep in line]
    if not hits:
        return "", line.strip()
    pos, sep = min(hits)
    return line[:pos].strip(), line[pos + len(sep) :].strip()
