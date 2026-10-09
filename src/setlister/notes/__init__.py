"""A short, interesting paragraph per track, grounded in facts gathered from open databases.

The text is written by an LLM through LiteLLM, so any provider works by changing one config
string. It is opt-in (`--llm-notes`), because a local model is slow on a laptop; the
suggested free model is Qwen 3 8B through Ollama. Without an LLM, or if none is reachable,
a plain factual sentence is produced instead, so a run never fails because of it.
"""

from __future__ import annotations

import json
import logging

from setlister.config import NotesConfig
from setlister.models import TrackRef

log = logging.getLogger(__name__)

PROMPT = """You write liner-note style blurbs for a DJ set tracklist.
Write ONE paragraph of at most {max_words} words about the track below that a listener would
find interesting (origin, label, scene, sample, the artist's story, how it was received).
Use ONLY the facts provided; if they are thin, keep it short and do not invent anything.
No hype words, no emojis, no preamble. Plain text only.

Track: {display}
Facts (JSON): {facts}
"""


def fallback_note(track: TrackRef, facts: dict) -> str | None:
    bits = []
    year = facts.get("year") or track.year or str(facts.get("first_release_date", ""))[:4] or None
    labels = facts.get("labels") or ([track.label] if track.label else [])
    if year and labels:
        bits.append(f"Released in {year} on {labels[0]}.")
    elif year:
        bits.append(f"Released in {year}.")
    elif labels:
        bits.append(f"Released on {labels[0]}.")
    styles = facts.get("styles") or facts.get("tags")
    if styles:
        bits.append("Filed under " + ", ".join(styles[:3]) + ".")
    return " ".join(bits) or None


def write_note(track: TrackRef, facts: dict, cfg: NotesConfig) -> tuple[str | None, str]:
    """Returns (note, how) where how is the model name or 'facts' for the fallback."""
    if not cfg.llm:
        return fallback_note(track, facts), "facts"
    try:
        import litellm

        litellm.suppress_debug_info = True
        resp = litellm.completion(
            model=cfg.model,
            api_base=cfg.api_base,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT.format(
                        max_words=cfg.max_words,
                        display=track.display,
                        facts=json.dumps(facts, ensure_ascii=False, default=str)[:4000],
                    ),
                }
            ],
            temperature=0.3,
            timeout=120,
            **_key_for(cfg.model),
        )
        text = resp.choices[0].message.content or ""
        text = _strip_thinking(text).strip()
        if text:
            return text, cfg.model
    except Exception as e:
        log.info("LLM note unavailable (%s); using facts only", type(e).__name__)
    return fallback_note(track, facts), "facts"


def _key_for(model: str) -> dict:
    from setlister.secrets import get_secret

    provider = model.split("/", 1)[0]
    key = get_secret(f"{provider}_api_key") if provider not in ("ollama", "ollama_chat") else None
    return {"api_key": key} if key else {}


def _strip_thinking(text: str) -> str:
    """Qwen 3 and similar emit <think>...</think> before the answer."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text
