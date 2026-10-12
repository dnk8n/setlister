"""Secret handling. Secrets never live in config files, output files or logs.

Lookup order for a secret named e.g. "discogs_token":
  1. environment variable SETLISTER_DISCOGS_TOKEN (a local, gitignored .env file is loaded too)
  2. the OS keychain (macOS Keychain, Secret Service, Windows Credential Locker) via `keyring`

`setlister config` writes to the keychain. Repo hooks (gitleaks) block commits/pushes containing
anything that looks like a credential, as a second line of defence.
"""

from __future__ import annotations

import contextlib
import logging
import os
from dataclasses import dataclass

import keyring
from dotenv import load_dotenv

SERVICE = "setlister"


@dataclass(frozen=True)
class SecretSpec:
    name: str
    unlocks: str
    signup_url: str
    free: bool = True


KNOWN_SECRETS: dict[str, SecretSpec] = {
    s.name: s
    for s in [
        SecretSpec(
            "acoustid_key",
            "AcoustID fingerprint lookups for unknown stretches of the mix",
            "https://acoustid.org/new-application",
        ),
        SecretSpec(
            "discogs_token",
            "Discogs release search: labels, years, credits and store links",
            "https://www.discogs.com/settings/developers",
        ),
        SecretSpec(
            "anthropic_api_key",
            "Paid LLM for track notes (only if notes.model starts with 'anthropic/')",
            "https://console.anthropic.com/settings/keys",
            free=False,
        ),
        SecretSpec(
            "openai_api_key",
            "Paid LLM for track notes (only if notes.model starts with 'openai/')",
            "https://platform.openai.com/api-keys",
            free=False,
        ),
        # TODO(paid recognisers): audd_token, acrcloud_key/acrcloud_secret
    ]
}

_loaded_dotenv = False


def env_var(name: str) -> str:
    return f"SETLISTER_{name.upper()}"


def get_secret(name: str) -> str | None:
    global _loaded_dotenv
    if not _loaded_dotenv:
        load_dotenv(override=False)
        _loaded_dotenv = True
    value = os.environ.get(env_var(name))
    if value:
        _register(value)
        return value
    try:
        value = keyring.get_password(SERVICE, name)
    except keyring.errors.KeyringError:
        value = None
    if value:
        _register(value)
    return value or None


def set_secret(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)


def delete_secret(name: str) -> None:
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(SERVICE, name)


def where_is(name: str) -> str | None:
    """Describe where a secret was found, without revealing it."""
    if os.environ.get(env_var(name)):
        return f"env {env_var(name)}"
    try:
        if keyring.get_password(SERVICE, name):
            return "keychain"
    except keyring.errors.KeyringError:
        return None
    return None


# --- redaction -----------------------------------------------------------------------------

_known_values: set[str] = set()


def _register(value: str) -> None:
    if len(value) >= 6:
        _known_values.add(value)


def redact(text: str) -> str:
    for v in _known_values:
        text = text.replace(v, "***")
    return text


class RedactingFilter(logging.Filter):
    """Attach to log handlers so a secret that sneaks into a message is masked."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Format first, then redact the result: redacting the arguments one by one turned
        # numbers into strings and broke '%d' placeholders.
        record.msg = redact(record.getMessage())
        record.args = None
        return True
