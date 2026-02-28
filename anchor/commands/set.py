"""
anc set — create local anchors.

Usage:
    anc set --path myproject                        # anchor current dir
    anc set --path myproject ~/code/proj            # anchor a specific path
    anc set --url  myapi https://api.example.com    # URL anchor
    anc set --ssh  prod  manu@192.168.1.10          # SSH anchor (key-based)
    anc set --ssh  prod  manu@192.168.1.10:2222     # custom port
    anc set --ssh  prod  manu@192.168.1.10 -i ~/.ssh/id_rsa

Common options:
    --note "text"          short description
    --groups dev,ops       visibility groups (server access control)
    --force                overwrite existing anchor without prompt
"""

from __future__ import annotations

import getpass
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.text import Text

from anchor.store import anchor_exists, save_anchor
from anchor.utils.meta import detect_docker, detect_git
from anchor.utils.output import err, info, out, warn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_groups(groups_str: str | None) -> list[str]:
    if not groups_str:
        return []
    return [g.strip() for g in groups_str.split(",") if g.strip()]


def set_anchor(
    args: Optional[list[str]] = typer.Argument(
        None,
        help="name [path | user@host[:port] | base_url]",
    ),
    # Type flags
    use_path: bool = typer.Option(False, "--path", "-p", help="Create a local path anchor"),
    use_url:  bool = typer.Option(False, "--url",  "-u", help="Create a URL anchor"),
    use_ssh:  bool = typer.Option(False, "--ssh",  "-s", help="Create an SSH anchor"),
    # Common
    note:       Optional[str] = typer.Option(None, "--note", "-n", help="Short description"),
    groups_str: Optional[str] = typer.Option(None, "--groups", "-g", help="Comma-separated groups (e.g. dev,ops)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing anchor without prompt"),
    # --path specific
    use_abs: bool = typer.Option(False, "--abs", help="Store absolute path (default: relative to ~)"),
    # --ssh specific
    identity: Optional[str] = typer.Option(None, "--identity", "-i", help="Path to SSH private key file"),
    port_opt:  Optional[int] = typer.Option(None, "--port",     help="SSH port (overrides port in user@host:port)"),
    ask_pass:  bool = typer.Option(False, "--password", help="Prompt for SSH password (stored in plaintext — prefer --pass-secret)"),
    key_secret:  Optional[str] = typer.Option(None, "--key-secret",  help="Vault path for private key (stores [[secret:path]])"),
    pass_secret: Optional[str] = typer.Option(None, "--pass-secret", help="Vault path for password   (stores [[secret:path]])"),
    no_test: bool = typer.Option(False, "--no-test", help="Skip SSH connection test"),
) -> None:
    """Create a local path, URL, or SSH anchor."""

    flags = [use_path, use_url, use_ssh]
    if sum(flags) == 0:
        err.print(
            "[yellow]Specify the anchor type:[/yellow]\n"
            "  anc set --path <name> [path]\n"
            "  anc set --url  <name> <base_url>\n"
            "  anc set --ssh  <name> user@host[:port]"
        )
        raise typer.Exit(1)

    if sum(flags) > 1:
        err.print("[red]✗ Use only one of --path / --url / --ssh.[/red]")
        raise typer.Exit(1)

    args = args or []
    groups = _parse_groups(groups_str)

    if use_path:
        _create_path_anchor(args, note, groups, use_abs, force)
    elif use_url:
        _create_url_anchor(args, note, groups, force)
    else:
        _create_ssh_anchor(args, note, groups, force, identity, port_opt,
                           ask_pass, key_secret, pass_secret, no_test)


# ---------------------------------------------------------------------------
# Local path anchor
# ---------------------------------------------------------------------------

def _create_path_anchor(
    args: list[str],
    note: str | None,
    groups: list[str],
    use_abs: bool,
    force: bool,
) -> None:
    if not args:
        abs_path = Path.cwd().resolve()
        name = abs_path.name
    elif len(args) == 1:
        raw = args[0]
        if _looks_like_path(raw):
            abs_path = Path(raw).expanduser().resolve()
            name = abs_path.name
        else:
            name = raw
            abs_path = Path.cwd().resolve()
    else:
        name = args[0]
        abs_path = Path(args[1]).expanduser().resolve()

    name = name.removesuffix(".json")

    if not abs_path.exists():
        err.print(f"[red]✗ Path does not exist:[/red] {abs_path}")
        raise typer.Exit(1)

    home = Path.home()
    if not use_abs and abs_path.is_relative_to(home):
        stored_path = "~/" + str(abs_path.relative_to(home))
    else:
        stored_path = str(abs_path)

    _check_overwrite(name, force)

    anchor: dict = {
        "type": "local",
        "name": name,
        "path": stored_path,
        "groups": groups,
        "created_at": _now(),
    }
    if note:
        anchor["note"] = note

    git_info = detect_git(abs_path)
    if git_info:
        anchor["git"] = git_info

    docker_info = detect_docker(abs_path)
    if docker_info:
        anchor["docker"] = docker_info

    save_anchor(name, anchor)

    body = Text()
    body.append("path   ", style="dim")
    body.append(stored_path, style="green")
    if git_info:
        body.append("\ngit    ", style="dim")
        body.append(git_info["branch"], style="cyan")
        if git_info.get("is_dirty"):
            body.append("  (dirty)", style="yellow")
        msg = git_info.get("commit", {}).get("message", "")
        if msg:
            body.append(f"\n       {msg}", style="dim")
    if docker_info:
        svcs = [s["name"] for s in docker_info.get("services", [])]
        body.append("\ndocker ", style="dim")
        body.append(", ".join(svcs) if svcs else "detected", style="bright_blue")
    if groups:
        body.append("\ngroups ", style="dim")
        body.append(", ".join(groups))

    out.print(Panel(body, title=f"[bold cyan]local[/bold cyan]  [bold]{name}[/bold]",
                    border_style="cyan", padding=(0, 1)))
    info(f"Saved → push with: [bold]anc push {name}[/bold]")


# ---------------------------------------------------------------------------
# URL anchor
# ---------------------------------------------------------------------------

def _create_url_anchor(
    args: list[str],
    note: str | None,
    groups: list[str],
    force: bool,
) -> None:
    if len(args) < 2:
        err.print(
            "[yellow]Usage:[/yellow] anc set --url <name> <base_url>\n"
            "[dim]Example: anc set --url myapi https://api.example.com[/dim]"
        )
        raise typer.Exit(1)

    name = args[0].removesuffix(".json")
    base_url = args[1].rstrip("/")

    if not base_url.startswith(("http://", "https://")):
        err.print(f"[red]✗ base_url must start with http:// or https://[/red]\n  Got: {base_url}")
        raise typer.Exit(1)

    _check_overwrite(name, force)

    anchor: dict = {
        "type": "url",
        "name": name,
        "base_url": base_url,
        "routes": [],
        "groups": groups,
        "created_at": _now(),
    }
    if note:
        anchor["note"] = note

    save_anchor(name, anchor)

    body = Text()
    body.append("base_url  ", style="dim")
    body.append(base_url, style="magenta")
    body.append("\nroutes    ", style="dim")
    body.append("(none)", style="dim italic")
    if groups:
        body.append("\ngroups    ", style="dim")
        body.append(", ".join(groups))

    out.print(Panel(body, title=f"[bold magenta]url[/bold magenta]  [bold]{name}[/bold]",
                    border_style="magenta", padding=(0, 1)))
    info(f"Saved → push with: [bold]anc push {name}[/bold]")


# ---------------------------------------------------------------------------
# SSH anchor
# ---------------------------------------------------------------------------

def _create_ssh_anchor(
    args: list[str],
    note: str | None,
    groups: list[str],
    force: bool,
    identity: str | None,
    port_opt: int | None,
    ask_pass: bool,
    key_secret: str | None,
    pass_secret: str | None,
    no_test: bool,
) -> None:
    if len(args) < 2:
        err.print(
            "[yellow]Usage:[/yellow] anc set --ssh <name> user@host[:port]\n"
            "[dim]Examples:\n"
            "  anc set --ssh prod manu@192.168.1.10\n"
            "  anc set --ssh prod manu@192.168.1.10:2222\n"
            "  anc set --ssh prod manu@192.168.1.10 -i ~/.ssh/id_rsa\n"
            "  anc set --ssh prod manu@192.168.1.10 --pass-secret vault/prod-pass[/dim]"
        )
        raise typer.Exit(1)

    name = args[0].removesuffix(".json")
    target = args[1]

    # Parse user@host[:port]
    try:
        user, host, port = _parse_ssh_target(target)
    except ValueError as exc:
        err.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(1)

    # --port flag overrides port from target
    if port_opt is not None:
        port = port_opt

    if port < 1 or port > 65535:
        err.print(f"[red]✗ Invalid port: {port}[/red]")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # Resolve auth credentials
    # ------------------------------------------------------------------

    # Key: precedence → --key-secret > -i/--identity > nothing
    key_val: str | None = None
    if key_secret:
        key_val = f"[[secret:{key_secret}]]"
    elif identity:
        key_path = Path(identity).expanduser()
        if not key_path.exists():
            err.print(f"[red]✗ Identity file not found:[/red] {key_path}")
            raise typer.Exit(1)
        key_val = str(key_path)

    # Password: precedence → --pass-secret > --password prompt > nothing
    password_val: str | None = None
    if pass_secret:
        password_val = f"[[secret:{pass_secret}]]"
    elif ask_pass:
        warn(
            "Storing a plaintext password in the anchor file is a security risk.\n"
            "  Consider using [bold]--pass-secret vault/my-pass[/bold] to keep it in the vault."
        )
        try:
            password_val = getpass.getpass(f"SSH password for {user}@{host}: ")
        except (EOFError, KeyboardInterrupt):
            err.print("\n[red]Aborted.[/red]")
            raise typer.Exit(1)
        if not password_val:
            err.print("[red]✗ Password cannot be empty.[/red]")
            raise typer.Exit(1)

    # ------------------------------------------------------------------
    # Test connection (unless --no-test)
    # ------------------------------------------------------------------
    if not no_test:
        out.print(f"[dim]Testing connection to {user}@{host}:{port}…[/dim]", end=" ")
        ok = _test_ssh(user, host, port, key_val if key_val and "[[secret" not in key_val else None)
        if ok:
            out.print("[green]OK[/green]")
        else:
            out.print("[red]failed[/red]")
            err.print(
                f"[red]✗ Could not connect to {user}@{host}:{port}[/red]\n"
                "  Check host, user, port and key, or use [bold]--no-test[/bold] to skip."
            )
            raise typer.Exit(1)

    _check_overwrite(name, force)

    # ------------------------------------------------------------------
    # Build anchor document
    # ------------------------------------------------------------------
    anchor: dict = {
        "type": "ssh",
        "name": name,
        "host": host,
        "user": user,
        "port": port,
        "groups": groups,
        "paths": [],
        "created_at": _now(),
    }
    if key_val:
        anchor["key"] = key_val
    if password_val:
        anchor["password"] = password_val
    if note:
        anchor["note"] = note

    save_anchor(name, anchor)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    body = Text()
    body.append("host     ", style="dim")
    body.append(host, style="cyan")
    body.append("\nuser     ", style="dim")
    body.append(user, style="cyan")
    body.append("\nport     ", style="dim")
    body.append(str(port), style="cyan" if port != 22 else "dim")

    if key_val:
        body.append("\nkey      ", style="dim")
        if "[[secret:" in key_val:
            body.append(key_val, style="green")
        else:
            body.append(key_val, style="yellow")

    if password_val:
        body.append("\npassword ", style="dim")
        if "[[secret:" in password_val:
            body.append(password_val, style="green")
        else:
            body.append("(stored — consider using --pass-secret)", style="yellow")

    if not key_val and not password_val:
        body.append("\nauth     ", style="dim")
        body.append("none specified (relies on ssh-agent or ~/.ssh/config)", style="dim italic")

    if groups:
        body.append("\ngroups   ", style="dim")
        body.append(", ".join(groups))

    out.print(Panel(body, title=f"[bold green]ssh[/bold green]  [bold]{name}[/bold]",
                    border_style="green", padding=(0, 1)))
    info(f"Saved → push with: [bold]anc push {name}[/bold]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ssh_target(target: str) -> tuple[str, str, int]:
    """
    Parse 'user@host' or 'user@host:port' → (user, host, port).
    Raises ValueError on bad format.
    """
    if "@" not in target:
        raise ValueError(f"Expected user@host[:port], got: {target!r}")

    user_part, rest = target.split("@", 1)
    if not user_part:
        raise ValueError("Username cannot be empty")

    # Port: check for ':port' suffix (but not IPv6 brackets)
    port = 22
    if ":" in rest and not rest.startswith("["):
        host_part, port_str = rest.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(f"Invalid port: {port_str!r}")
    else:
        host_part = rest

    if not host_part:
        raise ValueError("Hostname cannot be empty")

    return user_part, host_part, port


def _test_ssh(user: str, host: str, port: int, identity: str | None) -> bool:
    """Return True if a basic SSH connectivity check succeeds."""
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-o", "StrictHostKeyChecking=accept-new",
        "-p", str(port),
    ]
    if identity:
        cmd += ["-i", identity]
    cmd += [f"{user}@{host}", "exit"]

    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _looks_like_path(value: str) -> bool:
    return value.startswith(("/", "~", ".")) or os.sep in value


def _check_overwrite(name: str, force: bool) -> None:
    if not anchor_exists(name):
        return
    if force:
        return
    warn(f"Anchor [bold]{name}[/bold] already exists.")
    if not typer.confirm("Overwrite?", default=False):
        out.print("[dim]Aborted.[/dim]")
        raise typer.Exit(0)
