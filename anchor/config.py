"""
Configuration and credential management.

Config:      ~/.config/anchor/config.toml    (server URL, preferences)
Credentials: ~/.config/anchor/credentials.json (JWT token — 0600 permissions)
Data:        $ANCHOR_DIR or ~/.anchors/data   (local anchor JSON files)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _config_dir() -> Path:
    """XDG-compliant config directory. Respects $XDG_CONFIG_HOME on Linux,
    %APPDATA% on Windows."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "anchor"


def _data_dir() -> Path:
    """Local anchor JSON storage. Overridable via $ANCHOR_DIR."""
    return Path(os.environ.get("ANCHOR_DIR", Path.home() / ".anchors" / "data"))


CONFIG_DIR: Path = _config_dir()
DATA_DIR: Path = _data_dir()
CONFIG_FILE: Path = CONFIG_DIR / "config.toml"
CREDENTIALS_FILE: Path = CONFIG_DIR / "credentials.json"


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# TOML config (read with tomllib/tomli, write manually for zero extra deps)
# ---------------------------------------------------------------------------

def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        import tomllib  # stdlib in Python 3.11+
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _write_toml(data: dict, path: Path) -> None:
    """Write a simple nested TOML dict (one level of sections)."""
    lines: list[str] = []
    top_keys = {k: v for k, v in data.items() if not isinstance(v, dict)}
    sections = {k: v for k, v in data.items() if isinstance(v, dict)}

    for k, v in top_keys.items():
        lines.append(_toml_kv(k, v))

    for section, values in sections.items():
        lines.append(f"\n[{section}]")
        for k, v in values.items():
            lines.append(_toml_kv(k, v))

    path.write_text("\n".join(lines) + "\n")


def _toml_kv(key: str, value) -> str:
    if isinstance(value, bool):
        return f"{key} = {'true' if value else 'false'}"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key} = "{escaped}"'
    return f"{key} = {value}"


# ---------------------------------------------------------------------------
# Public config API
# ---------------------------------------------------------------------------

def load_config() -> dict:
    return _load_toml(CONFIG_FILE)


def save_config(data: dict) -> None:
    ensure_dirs()
    _write_toml(data, CONFIG_FILE)


def get_server_url() -> str | None:
    return load_config().get("server", {}).get("url")


def set_server_url(url: str) -> None:
    cfg = load_config()
    cfg.setdefault("server", {})["url"] = url.rstrip("/")
    save_config(cfg)


# ---------------------------------------------------------------------------
# Credentials (JWT token) — stored with 0600 permissions
# ---------------------------------------------------------------------------

def load_credentials() -> dict:
    if not CREDENTIALS_FILE.exists():
        return {}
    try:
        return json.loads(CREDENTIALS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_credentials(data: dict) -> None:
    ensure_dirs()
    CREDENTIALS_FILE.write_text(json.dumps(data, indent=2))
    if sys.platform != "win32":
        os.chmod(CREDENTIALS_FILE, 0o600)


def get_token() -> str | None:
    return load_credentials().get("token")


def set_token(token: str, expires_at: str | None = None) -> None:
    creds = load_credentials()
    creds["token"] = token
    if expires_at:
        creds["expires_at"] = expires_at
    else:
        creds.pop("expires_at", None)
    save_credentials(creds)


def clear_credentials() -> None:
    save_credentials({})
