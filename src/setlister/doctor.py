"""`setlister doctor`: check every optional piece and say what it unlocks and how to fix it.

`setlister run` calls this first, so a third-party user is guided through configuration
before any heavy work starts.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass

import requests

from setlister.config import Config
from setlister.secrets import KNOWN_SECRETS, where_is


@dataclass
class Check:
    name: str
    ok: bool
    required: bool
    detail: str
    fix: str = ""


def _ollama(cfg: Config) -> Check:
    model = cfg.notes.model
    if not cfg.notes.llm:
        return Check(
            "track notes", True, False, "facts only (add --llm-notes for LLM-written notes)"
        )
    if model.startswith("claude-code/"):
        return _claude_code(model)
    if importlib.util.find_spec("litellm") is None:
        return Check(
            "track notes (LLM)",
            False,
            False,
            "litellm not installed; notes will be plain facts",
            "pip install 'setlister[llm]'",
        )
    if not model.startswith(("ollama/", "ollama_chat/")):
        provider = model.split("/", 1)[0]
        found = where_is(f"{provider}_api_key")
        return Check(
            "track notes (LLM)",
            bool(found),
            False,
            f"{model} ({'key in ' + found if found else 'no API key'})",
            f"setlister config set {provider}_api_key",
        )
    base = cfg.notes.api_base or "http://localhost:11434"
    name = model.split("/", 1)[1]
    try:
        tags = requests.get(f"{base}/api/tags", timeout=2).json().get("models", [])
    except requests.RequestException:
        return Check(
            "track notes (local LLM)",
            False,
            False,
            "Ollama not running; notes will be plain facts",
            "install from https://ollama.com, then: ollama serve",
        )
    have = {t.get("name") for t in tags} | {t.get("model") for t in tags}
    if name not in have and f"{name}:latest" not in have:
        return Check(
            "track notes (local LLM)",
            False,
            False,
            f"model {name} not pulled",
            f"ollama pull {name}",
        )
    return Check("track notes (local LLM)", True, False, f"{model} via Ollama")


def _claude_code(model: str) -> Check:
    name = "track notes (Claude Code)"
    exe = shutil.which("claude")
    if not exe:
        return Check(
            name,
            False,
            False,
            "claude CLI not found; notes will be plain facts",
            "install Claude Code: https://code.claude.com/docs",
        )
    try:
        done = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=20)
        logged_in = bool(json.loads(done.stdout).get("loggedIn"))
    except (subprocess.SubprocessError, ValueError, OSError):
        logged_in = False
    if not logged_in:
        return Check(
            name,
            False,
            False,
            "claude CLI is not logged in; notes will be plain facts",
            "run `claude` once and complete /login",
        )
    return Check(name, True, False, f"{model} via your Claude login")


def run_checks(cfg: Config, *, network: bool = True) -> list[Check]:
    checks = [
        Check("python ≥ 3.11", sys.version_info >= (3, 11), True, sys.version.split()[0]),
        Check(
            "ffmpeg",
            bool(shutil.which("ffmpeg")),
            True,
            shutil.which("ffmpeg") or "missing",
            "brew install ffmpeg",
        ),
        Check(
            "ffprobe",
            bool(shutil.which("ffprobe")),
            True,
            shutil.which("ffprobe") or "missing",
            "brew install ffmpeg",
        ),
    ]
    if cfg.identify.acoustid:
        checks.append(
            Check(
                "fpcalc (AcoustID)",
                bool(shutil.which("fpcalc")),
                False,
                shutil.which("fpcalc") or "missing; AcoustID lookups skipped",
                "brew install chromaprint",
            )
        )
    if cfg.identify.shazam:
        ok = importlib.util.find_spec("shazamio") is not None
        checks.append(
            Check(
                "shazamio",
                ok,
                False,
                "installed" if ok else "missing",
                "pip install shazamio",
            )
        )
    for spec in KNOWN_SECRETS.values():
        if not spec.free:
            continue
        found = where_is(spec.name)
        checks.append(
            Check(
                f"key: {spec.name}",
                bool(found),
                False,
                f"{'found in ' + found if found else 'not set'}: {spec.unlocks}",
                f"get one free at {spec.signup_url}, then: setlister config set {spec.name}",
            )
        )
    checks.append(_ollama(cfg))
    if network and cfg.identify.acoustid and where_is("acoustid_key"):
        from setlister.identify.acoustid_rec import key_problem
        from setlister.secrets import get_secret

        problem = key_problem(get_secret("acoustid_key") or "")
        checks.append(
            Check(
                "AcoustID key accepted",
                problem is None,
                False,
                "accepted" if problem is None else "rejected by AcoustID",
                problem or "",
            )
        )
    if network:
        for name, url in [
            ("YouTube", "https://www.youtube.com"),
            ("MusicBrainz", "https://musicbrainz.org"),
            ("Bandcamp", "https://bandcamp.com"),
            ("Discogs", "https://api.discogs.com"),
        ]:
            try:
                ok = requests.head(url, timeout=5, allow_redirects=True).status_code < 500
            except requests.RequestException:
                ok = False
            checks.append(
                Check(
                    f"reach {name}",
                    ok,
                    name == "YouTube",
                    "ok" if ok else "unreachable",
                    "check your internet connection / proxy",
                )
            )
    return checks


def render(checks: list[Check]) -> bool:
    """Print a table; return False if a required check failed."""
    from rich.console import Console
    from rich.table import Table

    table = Table(title="setlister doctor", show_lines=False)
    table.add_column("")
    table.add_column("check")
    table.add_column("status")
    table.add_column("fix")
    for c in checks:
        mark = "[green]✓[/]" if c.ok else ("[red]✗[/]" if c.required else "[yellow]–[/]")
        table.add_row(mark, c.name, c.detail, "" if c.ok else c.fix)
    Console(stderr=True).print(table)
    return all(c.ok for c in checks if c.required)
