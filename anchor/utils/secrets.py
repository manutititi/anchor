"""
Secret resolution for [[secret:path]] markers.

Uses AnchorClient to fetch secrets from the vault at runtime.
Secret values are only held in memory and never written to disk.

Pattern accepted: [[secret:my/vault/path]] or [[ secret:my/vault/path ]]
The path may contain letters, digits, hyphens, underscores, dots, and slashes.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anchor.client import AnchorClient

# Matches [[secret:<path>]] with optional surrounding whitespace
_SECRET_RE = re.compile(r"\[\[\s*secret\s*:\s*([a-zA-Z0-9/_\-\.]+)\s*\]\]")


def resolve_field(value: str | None, client: "AnchorClient | None") -> str | None:
    """Resolve a single field value.

    If the value contains [[secret:...]] markers, they are replaced with the
    corresponding vault values fetched from the server.

    Returns None if value is None or empty.
    Raises RuntimeError if markers are found but no client is available.
    """
    if not value or not isinstance(value, str):
        return value
    if "[[secret:" not in value:
        return value
    if client is None:
        raise RuntimeError(
            "Anchor contains a [[secret:...]] reference but no server is configured.\n"
            "Run: anc login --url <server-url>"
        )
    return _resolve(value, client, {})


def resolve_secrets(text: str, client: "AnchorClient") -> str:
    """Replace all [[secret:path]] markers in text with vault values.

    Repeated references to the same path are fetched only once (per call).
    """
    return _resolve(text, client, {})


def _resolve(text: str, client: "AnchorClient", cache: dict[str, str]) -> str:
    def _sub(m: re.Match) -> str:
        path = m.group(1)
        if path not in cache:
            cache[path] = _fetch(path, client)
        return cache[path]

    return _SECRET_RE.sub(_sub, text)


def _fetch(path: str, client: "AnchorClient") -> str:
    """Fetch a secret's plaintext from the vault. Never cached across calls."""
    from anchor.client import AnchorClientError

    try:
        resp = client.get(f"/vault/{path}")
    except AnchorClientError as exc:
        raise RuntimeError(f"Failed to fetch secret '{path}': {exc}") from exc

    if resp.status_code == 404:
        raise RuntimeError(f"Secret not found in vault: {path}")
    if resp.status_code == 403:
        raise RuntimeError(f"Access denied to secret: {path}")
    if not resp.ok:
        raise RuntimeError(
            f"Server error fetching secret '{path}': HTTP {resp.status_code}"
        )

    return resp.json().get("plaintext", "")
