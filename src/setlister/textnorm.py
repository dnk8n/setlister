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


VARIOUS = {"various", "various artists", "va", "v a", "unknown", "unknown artist"}
_POSITION = re.compile(r"^\s*[A-Da-d]?\d{1,2}\s*[.)]\s+")  # vinyl/track position "B2. "
_BRACKETS = re.compile(r"\s*[(\[]([^()\[\]]+)[)\]]")


def tidy_artist_title(artist: str, title: str) -> tuple[str, str]:
    """Fix common tagging habits so names read like a tracklist:
    - 'Various' (or a remixer) as artist with 'Real Artist - Title' in the title field;
    - a leading release position such as 'B2. ';
    - the same mix name twice, e.g. 'Song (Club Mix) [Club Mix]'."""
    artist, title = (artist or "").strip(), (title or "").strip()
    title = _POSITION.sub("", title)
    if " - " in title or " – " in title:
        inner_artist, inner_title = split_artist_title(title)
        groups = " ".join(_BRACKETS.findall(inner_title)).lower()
        remixer = bool(artist) and norm(artist) in norm(groups)
        if norm(artist) in VARIOUS or not artist or remixer:
            artist, title = inner_artist, _POSITION.sub("", inner_title)
    seen: set[str] = set()

    def dedupe(m: re.Match) -> str:
        key = norm(m.group(1))
        if key in seen:
            return ""
        seen.add(key)
        return m.group(0)

    title = _BRACKETS.sub(dedupe, title).strip()
    return artist, title


def split_artist_title(line: str) -> tuple[str, str]:
    """'Artist - Title' -> ('Artist', 'Title'), splitting at the first separator.
    Falls back to ('', line)."""
    hits = [(line.find(sep), sep) for sep in (" - ", " – ", " — ", " -- ") if sep in line]
    if not hits:
        return "", line.strip()
    pos, sep = min(hits)
    return line[:pos].strip(), line[pos + len(sep) :].strip()
