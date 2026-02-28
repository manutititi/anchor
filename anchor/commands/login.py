"""
anc login — authenticate with the Anchor server.

Saves the JWT token to ~/.config/anchor/credentials.json (mode 0600).
Saves the server URL to ~/.config/anchor/config.toml.

Password is NEVER accepted via CLI argument to avoid shell history exposure.
"""

from __future__ import annotations

import getpass
from typing import Optional

import requests
import typer
from rich.panel import Panel

from anchor.config import (
    CONFIG_DIR,
    get_server_url,
    set_server_url,
    set_token,
)
from anchor.utils.output import err, out


def login(
    url: Optional[str] = typer.Option(
        None, "--url", "-u",
        help="Server URL (e.g. https://anchor.example.com:17017)",
    ),
    username: Optional[str] = typer.Option(
        None, "--user", "-U",
        help="Username",
    ),
) -> None:
    """Authenticate with the Anchor server and save credentials."""

    # ------------------------------------------------------------------
    # 1. Resolve server URL
    # ------------------------------------------------------------------
    server_url = url or get_server_url()
    if not server_url:
        server_url = typer.prompt("Server URL")
    server_url = server_url.rstrip("/")

    # Security warning for plain HTTP in non-local contexts
    is_local = any(
        server_url.startswith(prefix)
        for prefix in ("http://localhost", "http://127.", "http://[::1]")
    )
    if server_url.startswith("http://") and not is_local:
        err.print(
            "[yellow]Warning:[/yellow] connecting over unencrypted HTTP. "
            "Use HTTPS in production to protect credentials in transit."
        )

    # ------------------------------------------------------------------
    # 2. Credentials — password always via getpass (never a CLI arg)
    # ------------------------------------------------------------------
    if not username:
        username = typer.prompt("Username")

    try:
        password = getpass.getpass("Password: ")
    except (EOFError, KeyboardInterrupt):
        err.print("\n[red]Aborted.[/red]")
        raise typer.Exit(1)

    if not password:
        err.print("[red]Password cannot be empty.[/red]")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # 3. Authenticate
    # ------------------------------------------------------------------
    try:
        resp = requests.post(
            f"{server_url}/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
    except requests.exceptions.ConnectionError:
        err.print(f"[red]✗ Cannot connect to {server_url}[/red]")
        raise typer.Exit(1)
    except requests.exceptions.Timeout:
        err.print("[red]✗ Request timed out.[/red]")
        raise typer.Exit(1)

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        err.print(f"[red]✗ Authentication failed:[/red] {detail}")
        raise typer.Exit(1)

    data = resp.json()
    token = data.get("access_token")
    groups: list[str] = data.get("groups", [])
    user: str = data.get("username", username)

    if not token:
        err.print("[red]✗ Server did not return a token.[/red]")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # 4. Persist — URL in config.toml, token in credentials.json (0600)
    # ------------------------------------------------------------------
    set_server_url(server_url)
    set_token(token)

    groups_str = ", ".join(groups) if groups else "[dim](none)[/dim]"
    out.print(
        Panel(
            f"[green]Authenticated successfully[/green]\n\n"
            f"[dim]User:[/dim]    {user}\n"
            f"[dim]Groups:[/dim]  {groups_str}\n"
            f"[dim]Server:[/dim]  {server_url}\n"
            f"[dim]Config:[/dim]  {CONFIG_DIR}",
            title="[bold green]anc login[/bold green]",
            border_style="green",
        )
    )
