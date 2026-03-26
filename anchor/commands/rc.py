"""
anc rc — restore files from a files anchor to the filesystem.

Examples:
    anc rc myconfig                  # restore to cwd
    anc rc myconfig /opt/deploy      # restore to specific path
    anc rc myconfig --yes            # skip confirmation
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from anchor.store import load_anchor
from anchor.utils.output import err, info, out, success, warn

_PRIVILEGED_PREFIXES = ("/etc", "/usr", "/var", "/opt", "/root")


def rc(
    anchor_name: str = typer.Argument(..., help="Name of the files anchor to restore"),
    target: Optional[str] = typer.Argument(
        None, help="Target directory for relative paths (default: cwd)",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Restore files from a files anchor to the filesystem."""

    try:
        data = load_anchor(anchor_name)
    except FileNotFoundError:
        err.print(f"[red]Anchor '[bold]{anchor_name}[/bold]' not found.[/red]")
        raise typer.Exit(1)

    # Support both data.files and data.docker.files
    docker = data.get("docker", {})
    files: dict | None = docker.get("files") or data.get("files")
    scripts = data.get("scripts", {})

    if not files:
        err.print("[red]No files found in anchor.[/red]")
        raise typer.Exit(1)

    target_path = os.path.abspath(os.path.expanduser(target or "."))

    # Escalate to root if needed
    _escalate_if_needed(files, target_path, anchor_name)

    # Preview
    preview = _build_preview(files, target_path)
    if not preview:
        success("Nothing to do — all files already match.")
        return

    out.print(f"\n[cyan]The following files will be created or modified:[/cyan]\n")
    for tag, path in preview:
        color = {"NEW": "green", "CHG": "yellow", "MOD": "yellow", "DIR": "blue"}.get(tag, "white")
        out.print(f"  [{color}][{tag}][/{color}]  {path}")

    if not yes:
        confirmed = typer.confirm("\nContinue with these changes?", default=False)
        if not confirmed:
            out.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    # Execute
    _run_scripts(scripts.get("preload"), "preload")
    os.makedirs(target_path, exist_ok=True)

    changed, skipped = _apply_files(files, target_path)

    # env anchor symlink
    env_anchor = docker.get("env_anchor")
    if env_anchor:
        env_ref = os.path.join(target_path, ".anc_env")
        try:
            Path(env_ref).write_text(env_anchor.strip() + "\n")
            changed.append(env_ref)
        except OSError as exc:
            err.print(f"[red]Failed to write .anc_env: {exc}[/red]")

    _run_scripts(scripts.get("postload"), "postload")

    # Summary
    out.print()
    if changed:
        success(f"{len(changed)} file(s) modified/created from [bold]{anchor_name}[/bold]")
    if skipped:
        info(f"{len(skipped)} file(s) skipped (already up to date)")


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

def _escalate_if_needed(files: dict, target_path: str, anchor_name: str) -> None:
    """Re-exec as root if any destination path requires it."""
    if os.geteuid() == 0:
        return

    privileged = []
    for rel_path in files:
        dest = _resolve_dest(rel_path, target_path)
        if any(dest.startswith(p) for p in _PRIVILEGED_PREFIXES):
            privileged.append(dest)

    if not privileged:
        return

    err.print("[yellow]Some files target protected system paths:[/yellow]")
    for p in privileged[:5]:
        err.print(f"  {p}")
    if len(privileged) > 5:
        err.print(f"  [dim]... and {len(privileged) - 5} more[/dim]")

    if not typer.confirm("Re-run with sudo?", default=False):
        err.print("[red]Aborted.[/red]")
        raise typer.Exit(1)

    env = os.environ.copy()
    env.setdefault("ANCHOR_DIR", str(Path.home() / ".anchors" / "data"))

    args = [sys.executable, "-m", "anchor.cli", "rc", anchor_name, target_path, "--yes"]
    os.execve("/usr/bin/sudo", ["sudo", "-E"] + args, env)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def _build_preview(files: dict, target_path: str) -> list[tuple[str, str]]:
    """Build a list of (tag, dest_path) describing pending changes."""
    changes: list[tuple[str, str]] = []

    for rel_path, meta in files.items():
        dest = _resolve_dest(rel_path, target_path)

        if meta.get("type") == "directory":
            if not os.path.isdir(dest):
                changes.append(("DIR", dest))
            continue

        if not os.path.exists(dest):
            changes.append(("NEW", dest))
            continue

        mode = meta.get("mode", "replace")
        if mode == "replace":
            content = meta.get("content", "")
            encoding = meta.get("encoding", "plain")
            decoded = base64.b64decode(content) if encoding == "base64" else content.encode()
            try:
                current = Path(dest).read_bytes()
                if hashlib.md5(current).digest() != hashlib.md5(decoded).digest():
                    changes.append(("CHG", dest))
            except OSError:
                changes.append(("CHG", dest))
        else:
            changes.append(("MOD", dest))

    return changes


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def _apply_files(files: dict, target_path: str) -> tuple[list[str], list[str]]:
    """Write all files. Returns (changed, skipped) lists."""
    changed: list[str] = []
    skipped: list[str] = []

    for rel_path, meta in files.items():
        dest = _resolve_dest(rel_path, target_path)

        # Directory
        if meta.get("type") == "directory":
            try:
                os.makedirs(dest, exist_ok=True)
                if meta.get("perm"):
                    os.chmod(dest, int(meta["perm"], 8))
                _apply_ownership(dest, meta)
                changed.append(dest)
            except OSError as exc:
                err.print(f"[red]Failed to create dir {dest}: {exc}[/red]")
            continue

        # Ensure parent
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        # External download
        if meta.get("external"):
            url = meta.get("path", "")
            if url:
                _download(url, dest, changed)
            continue

        # Write content
        wrote = _write_content(dest, meta, changed, skipped)

        # Permissions + ownership
        if meta.get("perm") and os.path.isfile(dest):
            try:
                os.chmod(dest, int(meta["perm"], 8))
            except OSError as exc:
                warn(f"Failed to set permissions on {dest}: {exc}")

        _apply_ownership(dest, meta)

    return changed, skipped


def _write_content(dest: str, meta: dict, changed: list, skipped: list) -> bool:
    """Write a single file. Returns True on success."""
    content = meta.get("content", "")
    encoding = meta.get("encoding", "plain")
    mode = meta.get("mode", "replace")

    try:
        decoded = base64.b64decode(content) if encoding == "base64" else content.encode()
    except Exception as exc:
        err.print(f"[red]Decode error for {dest}: {exc}[/red]")
        return False

    try:
        if mode == "replace":
            if os.path.exists(dest):
                current = Path(dest).read_bytes()
                if hashlib.md5(current).digest() == hashlib.md5(decoded).digest():
                    skipped.append(dest)
                    return True
            Path(dest).write_bytes(decoded)
            changed.append(dest)

        elif mode == "append":
            with open(dest, "ab") as f:
                f.write(decoded)
            changed.append(dest)

        elif mode == "prepend":
            existing = Path(dest).read_bytes() if os.path.exists(dest) else b""
            Path(dest).write_bytes(decoded + existing)
            changed.append(dest)

        elif mode == "regex":
            regex = meta.get("regex", "")
            if not os.path.exists(dest):
                err.print(f"[red]Cannot apply regex — file missing: {dest}[/red]")
                return False
            original = Path(dest).read_text()
            result = re.sub(regex, decoded.decode(), original, flags=re.MULTILINE)
            Path(dest).write_text(result)
            changed.append(dest)

        else:
            err.print(f"[red]Unknown mode '{mode}' for {dest}[/red]")
            return False

        return True
    except Exception as exc:
        err.print(f"[red]Failed to write {dest}: {exc}[/red]")
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_dest(rel_path: str, target_path: str) -> str:
    """Resolve a relative path from the anchor to an absolute destination."""
    is_absolute = rel_path.startswith("~") or rel_path.startswith("/")
    if is_absolute:
        return os.path.normpath(os.path.expanduser(rel_path))
    return os.path.normpath(os.path.join(target_path, rel_path))


def _apply_ownership(dest: str, meta: dict) -> None:
    """Set owner/group if specified in metadata."""
    import grp
    import pwd

    try:
        uid = -1
        gid = -1
        if "owner" in meta:
            uid = pwd.getpwnam(meta["owner"]).pw_uid if isinstance(meta["owner"], str) else int(meta["owner"])
        if "group" in meta:
            gid = grp.getgrnam(meta["group"]).gr_gid if isinstance(meta["group"], str) else int(meta["group"])
        if uid != -1 or gid != -1:
            os.chown(dest, uid, gid)
    except (KeyError, OSError):
        pass


def _download(url: str, dest: str, changed: list) -> bool:
    """Download a file from a URL."""
    import urllib.request
    try:
        with urllib.request.urlopen(url) as resp:
            Path(dest).write_bytes(resp.read())
        changed.append(dest)
        return True
    except Exception as exc:
        err.print(f"[red]Failed to download {url}: {exc}[/red]")
        return False


def _run_scripts(blocks: list | None, phase: str) -> None:
    """Execute pre/post-load script blocks."""
    if not blocks:
        return
    info(f"Running {phase} scripts...")
    for script in blocks:
        if isinstance(script, str):
            cmd, scope = script, "."
        else:
            cmd = script.get("run", "")
            scope = script.get("scope", ".")

        scope = os.path.expanduser(scope)
        out.print(f"  [dim]cd {scope} && {cmd}[/dim]")
        try:
            subprocess.run(cmd, cwd=scope, shell=True, check=True)
        except subprocess.CalledProcessError as exc:
            err.print(f"[red]Script failed in {scope}: {exc}[/red]")
