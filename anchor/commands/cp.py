"""
anc cp — copy files between anchors and filesystem paths via rsync.

Supports: local→local, local→ssh, ssh→local, ssh→ssh.
SSH credentials (keys/passwords) are resolved from the vault and
handled in-memory only (ssh-agent temporal / sshpass pipe).

Examples:
    anc cp myproject/src /tmp/backup           # local anchor → local path
    anc cp ./file.txt remote-server/deploy/    # local file → ssh anchor
    anc cp remote-server/logs/ ./logs          # ssh anchor → local path
    anc cp server-a/data server-b/data         # ssh → ssh (via relay)
    anc cp myproject remote --exclude .git --exclude node_modules
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
from typing import Optional

import typer

from anchor.client import AnchorClient, AnchorClientError, NotAuthenticatedError
from anchor.store import load_anchor
from anchor.utils.output import err, info, out, success, warn
from anchor.utils.secrets import resolve_field


def cp(
    sources: list[str] = typer.Argument(..., help="Source path(s): anchor/subpath or local path"),
    destination: str = typer.Argument(..., help="Destination: anchor/subpath or local path"),
    exclude: Optional[list[str]] = typer.Option(
        None, "--exclude", "-e",
        help="Exclude pattern(s) passed to rsync (repeatable)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n",
        help="Show what would be transferred without copying",
    ),
) -> None:
    """Copy files between anchors and local paths via rsync."""

    if not shutil.which("rsync"):
        err.print("[red]rsync not found. Install it: sudo apt install rsync[/red]")
        raise typer.Exit(1)

    client = _try_client()

    dst = _resolve_endpoint(destination, client)

    for src_spec in sources:
        src = _resolve_endpoint(src_spec, client)
        _do_copy(src, dst, exclude or [], dry_run)


# ---------------------------------------------------------------------------
# Endpoint resolution
# ---------------------------------------------------------------------------

class _Endpoint:
    """Represents a local or SSH rsync endpoint."""

    def __init__(
        self,
        path: str,
        *,
        is_ssh: bool = False,
        host: str = "",
        user: str = "",
        port: int = 22,
        key_str: str | None = None,
        password: str | None = None,
        label: str = "",
    ):
        self.path = path
        self.is_ssh = is_ssh
        self.host = host
        self.user = user
        self.port = port
        self.key_str = key_str      # PEM in memory or file path
        self.password = password     # plaintext in memory
        self.label = label or path

    @property
    def rsync_path(self) -> str:
        if self.is_ssh:
            return f"{self.user}@{self.host}:{self.path}"
        return self.path


def _resolve_endpoint(spec: str, client: AnchorClient | None) -> _Endpoint:
    """Parse 'anchor_name/subpath' or a plain filesystem path."""
    # Split on first '/' to check if prefix is an anchor name
    parts = spec.split("/", 1)
    anchor_name = parts[0]
    subpath = parts[1] if len(parts) > 1 else ""

    # Try loading as anchor
    try:
        data = load_anchor(anchor_name)
    except FileNotFoundError:
        # Not an anchor — treat entire spec as a filesystem path
        resolved = os.path.abspath(os.path.expanduser(spec))
        return _Endpoint(resolved, label=spec)

    anchor_type = data.get("type", "")

    if anchor_type == "ssh":
        host = data.get("host", "")
        user = data.get("user", "")
        port = data.get("port", 22) or 22

        # Resolve credentials from vault (in-memory only)
        raw_key = data.get("key") or data.get("identity_file")
        raw_pass = data.get("password")
        key_str = resolve_field(raw_key, client)
        password = resolve_field(raw_pass, client)

        # Base path from anchor
        base = data.get("path") or "~"
        if base == "~" or not base:
            remote_path = subpath or "~"
        else:
            remote_path = os.path.join(base, subpath) if subpath else base

        return _Endpoint(
            remote_path,
            is_ssh=True,
            host=host,
            user=user,
            port=port,
            key_str=key_str,
            password=password,
            label=spec,
        )

    elif anchor_type == "local":
        local_path = os.path.expanduser(data.get("path", "."))
        if subpath:
            local_path = os.path.join(local_path, subpath)
        return _Endpoint(os.path.abspath(local_path), label=spec)

    else:
        err.print(f"[red]Anchor '[bold]{anchor_name}[/bold]' is type '{anchor_type}' — cp only supports local and ssh.[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Copy execution
# ---------------------------------------------------------------------------

def _do_copy(src: _Endpoint, dst: _Endpoint, excludes: list[str], dry_run: bool) -> None:
    """Execute rsync between two endpoints."""

    # Build base rsync args
    args = ["rsync", "-az", "--progress"]
    if dry_run:
        args.append("--dry-run")
    for pattern in excludes:
        args.extend(["--exclude", pattern])

    direction = f"{'ssh' if src.is_ssh else 'local'} → {'ssh' if dst.is_ssh else 'local'}"
    info(f"[bold]{src.label}[/bold] → [bold]{dst.label}[/bold]  [dim]({direction})[/dim]")

    if src.is_ssh and dst.is_ssh:
        _copy_ssh_to_ssh(src, dst, args)
    elif src.is_ssh:
        _copy_with_ssh(src, dst, args, ssh_endpoint=src)
    elif dst.is_ssh:
        _copy_with_ssh(src, dst, args, ssh_endpoint=dst)
    else:
        _copy_local(src, dst, args)


def _copy_local(src: _Endpoint, dst: _Endpoint, args: list[str]) -> None:
    """Local → local rsync."""
    # Ensure destination parent exists
    os.makedirs(dst.path, exist_ok=True)

    full = args + [_trail(src.path), dst.path + "/"]
    rc = subprocess.run(full).returncode
    if rc == 0:
        success(f"Copied [bold]{src.label}[/bold] → [bold]{dst.label}[/bold]")
    else:
        err.print(f"[red]rsync failed (exit {rc})[/red]")
        raise typer.Exit(rc)


def _copy_with_ssh(
    src: _Endpoint,
    dst: _Endpoint,
    args: list[str],
    *,
    ssh_endpoint: _Endpoint,
) -> None:
    """Local↔SSH rsync using ssh-agent temporal or sshpass."""
    key_str = ssh_endpoint.key_str
    password = ssh_endpoint.password
    port = ssh_endpoint.port

    if key_str and _is_pem(key_str):
        _rsync_via_agent(src, dst, args, port, key_str)
    elif key_str:
        # File path key
        ssh_cmd = f"ssh -i {os.path.expanduser(key_str)} -p {port} -o StrictHostKeyChecking=accept-new"
        _run_rsync(args + ["-e", ssh_cmd, src.rsync_path, _ensure_dst(dst)])
    elif password:
        _rsync_with_password(src, dst, args, port, password)
    else:
        # System ssh defaults
        ssh_cmd = f"ssh -p {port} -o StrictHostKeyChecking=accept-new"
        _run_rsync(args + ["-e", ssh_cmd, src.rsync_path, _ensure_dst(dst)])


def _copy_ssh_to_ssh(src: _Endpoint, dst: _Endpoint, args: list[str]) -> None:
    """SSH → SSH via local relay (rsync through pipes)."""
    info("[dim]SSH→SSH: relaying through local machine...[/dim]")

    with tempfile.TemporaryDirectory(prefix="anc-cp-") as tmpdir:
        relay = os.path.join(tmpdir, "relay")
        os.makedirs(relay)

        # Pull from source
        info(f"[dim]  1/2: pulling from {src.label}...[/dim]")
        pull_args = ["rsync", "-az"]
        for ex in [a for i, a in enumerate(args) if a == "--exclude"]:
            pass
        # Re-extract excludes from args
        excludes = []
        it = iter(args)
        for a in it:
            if a == "--exclude":
                excludes.extend(["--exclude", next(it, "")])

        pull_src = _Endpoint(src.path, is_ssh=True, host=src.host, user=src.user,
                             port=src.port, key_str=src.key_str, password=src.password,
                             label=src.label)
        pull_dst = _Endpoint(relay + "/", label="relay")
        _copy_with_ssh(pull_src, pull_dst, ["rsync", "-az"] + excludes, ssh_endpoint=pull_src)

        # Push to destination
        info(f"[dim]  2/2: pushing to {dst.label}...[/dim]")
        push_src = _Endpoint(relay + "/", label="relay")
        push_dst = _Endpoint(dst.path, is_ssh=True, host=dst.host, user=dst.user,
                             port=dst.port, key_str=dst.key_str, password=dst.password,
                             label=dst.label)
        _copy_with_ssh(push_src, push_dst, ["rsync", "-az", "--progress"] + excludes, ssh_endpoint=push_dst)

    success(f"Copied [bold]{src.label}[/bold] → [bold]{dst.label}[/bold] (via relay)")


# ---------------------------------------------------------------------------
# SSH agent strategy (PEM key in memory only)
# ---------------------------------------------------------------------------

def _rsync_via_agent(
    src: _Endpoint,
    dst: _Endpoint,
    args: list[str],
    port: int,
    key_str: str,
) -> None:
    """Run rsync using a temporary ssh-agent with the PEM key loaded in RAM."""
    from anchor.handlers.ssh import _normalize_pem, _parse_agent_pid

    for binary in ("ssh-agent", "ssh-add"):
        if not shutil.which(binary):
            raise RuntimeError(f"{binary} not found. Install openssh-client.")

    with tempfile.TemporaryDirectory(prefix="anc-") as tmpdir:
        os.chmod(tmpdir, 0o700)
        sock = os.path.join(tmpdir, "agent.sock")

        r = subprocess.run(["ssh-agent", "-a", sock], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Failed to start ssh-agent: {r.stderr.strip()}")

        agent_pid = _parse_agent_pid(r.stdout)
        env = {**os.environ, "SSH_AUTH_SOCK": sock}

        try:
            key_bytes = _normalize_pem(key_str).encode()
            add = subprocess.run(["ssh-add", "-"], input=key_bytes, env=env, stderr=subprocess.PIPE)
            if add.returncode != 0:
                raise RuntimeError(f"Failed to load key into agent: {add.stderr.decode().strip()}")

            ssh_cmd = f"ssh -p {port} -o StrictHostKeyChecking=accept-new"
            full = args + ["-e", ssh_cmd, src.rsync_path, _ensure_dst(dst)]
            subprocess.run(full, env=env)

        finally:
            if agent_pid:
                try:
                    os.kill(agent_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass


# ---------------------------------------------------------------------------
# Password strategy (sshpass pipe)
# ---------------------------------------------------------------------------

def _rsync_with_password(
    src: _Endpoint,
    dst: _Endpoint,
    args: list[str],
    port: int,
    password: str,
) -> None:
    """Run rsync using sshpass with password piped via fd."""
    if not shutil.which("sshpass"):
        warn("sshpass not found — rsync may prompt for password interactively.")
        ssh_cmd = f"ssh -p {port} -o StrictHostKeyChecking=accept-new"
        _run_rsync(args + ["-e", ssh_cmd, src.rsync_path, _ensure_dst(dst)])
        return

    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, (password + "\n").encode())
        os.close(w_fd)
        w_fd = -1

        ssh_cmd = f"ssh -p {port} -o StrictHostKeyChecking=accept-new"
        full = ["sshpass", "-d", str(r_fd)] + args + ["-e", ssh_cmd, src.rsync_path, _ensure_dst(dst)]
        subprocess.run(full, pass_fds=(r_fd,))
    finally:
        for fd in (w_fd, r_fd):
            if fd != -1:
                try:
                    os.close(fd)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_rsync(full_args: list[str]) -> None:
    """Run rsync and check exit code."""
    rc = subprocess.run(full_args).returncode
    if rc != 0:
        err.print(f"[red]rsync failed (exit {rc})[/red]")
        raise typer.Exit(rc)
    # success message printed by caller


def _trail(path: str) -> str:
    """Ensure a source path has trailing / for directory content copy."""
    if os.path.isdir(path) and not path.endswith("/"):
        return path + "/"
    return path


def _ensure_dst(ep: _Endpoint) -> str:
    """Return rsync destination string, ensuring trailing /."""
    p = ep.rsync_path
    if not ep.is_ssh and os.path.isdir(p) and not p.endswith("/"):
        return p + "/"
    if not p.endswith("/"):
        return p + "/"
    return p


def _is_pem(text: str) -> bool:
    return text.strip().startswith("-----BEGIN")


def _try_client() -> AnchorClient | None:
    try:
        return AnchorClient()
    except (AnchorClientError, NotAuthenticatedError):
        return None
