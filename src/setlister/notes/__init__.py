"""A short, interesting paragraph per track, grounded in facts gathered from open databases.

The text is written by an LLM, chosen with one config string (`notes.model`):

- `claude-code/<model>` runs the Claude Code CLI headless (`claude -p`), so it uses the
  subscription you are already logged in with and needs no API key. `<model>` is whatever
  the CLI's `--model` accepts, such as `haiku` or `sonnet`.
- anything else is a LiteLLM model string, e.g. `anthropic/claude-haiku-5-5` (API key in the
  keychain) or the free local `ollama/qwen3:8b`.

It is opt-in (`--llm-notes`). Without an LLM, or if none answers, a plain factual sentence is
produced instead, so a run never fails because of it. Notes are never cached: every run
writes them from scratch.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile

from setlister.config import NotesConfig
from setlister.models import TrackRef

log = logging.getLogger(__name__)

PROMPT = """You write liner-note style blurbs for a DJ set tracklist.
Write ONE paragraph of at most {max_words} words about the track below that a listener would
find interesting (origin, label, scene, sample, the artist's story, how it was received).
Use ONLY the facts provided; if they are thin, keep it short and do not invent anything.
No hype words, no emojis, no preamble. Never mention the facts, their limits or these
instructions. Plain text only.

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
    prompt = PROMPT.format(
        max_words=cfg.max_words,
        display=track.display,
        facts=json.dumps(facts, ensure_ascii=False, default=str)[:4000],
    )
    try:
        if cfg.model.startswith(CLAUDE_CODE):
            text = _claude_code(prompt, cfg.model.removeprefix(CLAUDE_CODE))
        else:
            text = _litellm(prompt, cfg)
        text = _strip_thinking(text).strip()
        if text:
            return text, cfg.model
    except Exception as e:
        log.info("LLM note unavailable (%s); using facts only", type(e).__name__)
    return fallback_note(track, facts), "facts"


CLAUDE_CODE = "claude-code/"


def _claude_code(prompt: str, model: str, timeout: float = 120) -> str:
    """One headless Claude Code turn with no tools, run in an empty folder so it reads nothing."""
    exe = shutil.which("claude")
    if not exe:
        raise FileNotFoundError("claude")
    with tempfile.TemporaryDirectory() as cwd:
        done = subprocess.run(
            [exe, "-p", prompt, "--model", model, "--output-format", "text"]
            + ["--tools", "", "--strict-mcp-config", "--no-session-persistence"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    if done.returncode != 0:
        raise RuntimeError(f"claude exited with {done.returncode}")
    return done.stdout


def _litellm(prompt: str, cfg: NotesConfig) -> str:
    import litellm

    litellm.suppress_debug_info = True
    resp = litellm.completion(
        model=cfg.model,
        api_base=cfg.api_base,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        timeout=120,
        **_key_for(cfg.model),
    )
    return resp.choices[0].message.content or ""


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
