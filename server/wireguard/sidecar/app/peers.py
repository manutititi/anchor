"""
Peer metadata persistence.

The WireGuard kernel module only stores public keys. Human-readable names
and any extra metadata are kept in a local JSON file so they survive
container restarts (the file lives on the mounted /config volume).
"""

import json
import threading
from pathlib import Path
from typing import Any

METADATA_PATH = Path("/config/peers_metadata.json")

_lock = threading.Lock()


def _read() -> dict[str, Any]:
    """Load the metadata file, returning an empty dict if missing or corrupt."""
    if not METADATA_PATH.exists():
        return {}
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict[str, Any]) -> None:
    """Atomically write the metadata file."""
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = METADATA_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(METADATA_PATH)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_metadata() -> dict[str, Any]:
    """Return the full metadata dict (pubkey → {name, ...})."""
    with _lock:
        return _read()


def get_name(pubkey: str) -> str | None:
    """Return the human-readable name for a pubkey, or None."""
    meta = load_metadata()
    entry = meta.get(pubkey)
    if isinstance(entry, dict):
        return entry.get("name")
    return None


def set_peer(pubkey: str, name: str) -> None:
    """Create or update the metadata entry for a peer."""
    with _lock:
        data = _read()
        data[pubkey] = {"name": name}
        _write(data)


def delete_peer(pubkey: str) -> bool:
    """Remove a peer's metadata. Returns True if the entry existed."""
    with _lock:
        data = _read()
        if pubkey not in data:
            return False
        del data[pubkey]
        _write(data)
        return True
