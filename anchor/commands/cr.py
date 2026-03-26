"""
anc cr — capture files/directories into a files anchor.

Examples:
    anc cr myconfig /etc/nginx/nginx.conf
    anc cr snapshot .
    anc cr myapp src/ --mode replace
    anc cr templates /etc/hosts --mode regex --blank
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from anchor.store import anchor_exists, anchor_path, save_anchor
from anchor.utils.output import err, info, out, success, warn

_VALID_MODES = {"replace", "append", "prepend", "regex"}
_PRIVILEGED_PREFIXES = ("/etc", "/usr", "/var", "/opt", "/root")


def cr(
    name: str = typer.Argument(..., help="Name for the files anchor"),
    paths: Optional[list[str]] = typer.Argument(
        None, help="Paths to capture (files or directories). Defaults to current dir.",
    ),
    mode: str = typer.Option(
        "replace", "--mode", "-m",
        help="Write mode: replace, append, prepend, regex",
    ),
    blank: bool = typer.Option(
        False, "--blank",
        help="Capture file metadata without content (skeleton)",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing anchor without prompting",
    ),
) -> None:
    """Capture files and directories into a files anchor."""

    if mode not in _VALID_MODES:
        err.print(f"[red]Invalid mode '[bold]{mode}[/bold]'. Choose from: {', '.join(sorted(_VALID_MODES))}[/red]")
        raise typer.Exit(1)

    # Default to cwd if no paths given
    if not paths:
        cwd = os.getcwd()
        info(f"No paths given, capturing current directory: [bold]{cwd}[/bold]")
        paths = ["."]
        path_display = "."
    else:
        path_display = paths if len(paths) > 1 else paths[0]

    # Validate paths exist
    for p in paths:
        resolved = _resolve(p)
        if not os.path.exists(resolved):
            err.print(f"[red]Path not found: [bold]{p}[/bold][/red]")
            raise typer.Exit(1)

    # Check overwrite
    if not force and anchor_exists(name):
        overwrite = typer.confirm(f"Anchor '{name}' already exists. Overwrite?", default=False)
        if not overwrite:
            out.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    if mode == "regex":
        warn("Regex mode: remember to manually define 'regex' patterns in the anchor JSON after capture.")

    # Build files dict
    files_dict = _build_files(paths, mode, blank)
    if not files_dict:
        err.print("[red]No files captured.[/red]")
        raise typer.Exit(1)

    user = os.getenv("USER") or "unknown"
    anchor_data = {
        "type": "files",
        "name": name,
        "path": path_display,
        "files": files_dict,
        "scripts": {"preload": [], "postload": []},
        "created_by": user,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "updated_by": user,
    }

    save_anchor(name, anchor_data)

    file_count = sum(1 for v in files_dict.values() if v.get("type") != "directory")
    dir_count = sum(1 for v in files_dict.values() if v.get("type") == "directory")

    summary = f"Anchor [bold]{name}[/bold] saved — {file_count} file(s)"
    if dir_count:
        summary += f", {dir_count} dir(s)"
    success(summary)
    out.print(f"  [dim]{anchor_path(name)}[/dim]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve(raw: str) -> str:
    """Expand ~ and resolve to absolute."""
    return os.path.abspath(os.path.expanduser(raw))


def _as_relative_to_home(path: str) -> str:
    """Convert absolute path under $HOME to ~/relative form."""
    resolved = _resolve(path)
    home = os.path.expanduser("~")
    if resolved.startswith(home + "/"):
        return "~/" + os.path.relpath(resolved, home)
    return resolved


def _should_become(path: str) -> bool:
    return any(path.startswith(p) for p in _PRIVILEGED_PREFIXES)


def _get_perm(path: str) -> str:
    try:
        return format(os.stat(path).st_mode & 0o7777, "04o")
    except OSError:
        return "0644"


def _encode_file(filepath: str) -> tuple[str | None, str | None]:
    """Read file and return (content, encoding). Binary → base64."""
    try:
        raw = Path(filepath).read_bytes()
        try:
            return raw.decode(), "plain"
        except UnicodeDecodeError:
            return base64.b64encode(raw).decode(), "base64"
    except OSError as exc:
        err.print(f"[red]Failed to read {filepath}: {exc}[/red]")
        return None, None


def _build_files(paths: list[str], mode: str, blank: bool) -> dict:
    """Build the files dict from a list of filesystem paths."""
    files_dict: dict = {}

    for raw_path in paths:
        resolved = _resolve(raw_path)

        if os.path.isfile(resolved):
            # Single file: use ~/relative or absolute key
            key = os.path.normpath(_as_relative_to_home(raw_path))
            entry = _make_entry(resolved, key, mode, blank)
            if entry:
                files_dict[key] = entry

        elif os.path.isdir(resolved):
            # Directory: keys are relative to the captured dir root.
            # e.g. capturing "." in /home/manu/own/testing → keys are "1/1.txt", "2/2.txt"
            for root, dirs, filenames in os.walk(resolved):
                rel_root = os.path.relpath(root, resolved)

                # Track empty directories
                if not filenames and not dirs:
                    dir_key = (rel_root + "/") if rel_root != "." else "./"
                    files_dict[dir_key] = {
                        "type": "directory",
                        "mode": "ensure",
                        "become": _should_become(os.path.join(resolved, rel_root)),
                        "perm": _get_perm(root),
                    }

                for fname in filenames:
                    full = os.path.join(root, fname)
                    key = os.path.normpath(os.path.relpath(full, resolved))
                    entry = _make_entry(full, key, mode, blank)
                    if entry:
                        files_dict[key] = entry

    return files_dict


def _make_entry(filepath: str, key: str, mode: str, blank: bool) -> dict | None:
    """Create a single file entry for the anchor."""
    content, encoding = _encode_file(filepath)
    if encoding is None:
        return None

    entry: dict = {"mode": mode}
    if mode == "regex":
        entry["submode"] = "replace"
        entry["regex"] = ""
        entry["content"] = ""
    else:
        entry["content"] = "" if blank else content

    entry["encoding"] = encoding
    entry["become"] = _should_become(key)
    entry["perm"] = _get_perm(filepath)
    return entry
