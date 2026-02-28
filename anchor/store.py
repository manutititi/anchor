"""
Local anchor store — read/write/list JSON anchor files from DATA_DIR.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterator

from anchor.config import DATA_DIR


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def anchor_path(name: str) -> Path:
    """Return the full path to an anchor JSON file."""
    stem = name.removesuffix(".json")
    return DATA_DIR / f"{stem}.json"


def anchor_exists(name: str) -> bool:
    return anchor_path(name).exists()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def load_anchor(name: str) -> dict:
    path = anchor_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Anchor '{name}' not found in {DATA_DIR}")
    return json.loads(path.read_text())


def save_anchor(name: str, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    anchor_path(name).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def delete_anchor(name: str) -> bool:
    path = anchor_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Listing / filtering
# ---------------------------------------------------------------------------

def iter_anchors() -> Iterator[tuple[str, dict]]:
    """Yield (name, data) for every valid JSON file in DATA_DIR."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(DATA_DIR.glob("*.json")):
        try:
            yield f.stem, json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue


def list_anchors(
    filter_fn: Callable[[dict], bool] | None = None,
) -> list[tuple[str, dict]]:
    """Return list of (name, data) tuples, optionally filtered."""
    return [
        (name, data)
        for name, data in iter_anchors()
        if filter_fn is None or filter_fn(data)
    ]
