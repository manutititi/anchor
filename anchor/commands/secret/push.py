"""anc secret push — create a new secret in the vault."""

from __future__ import annotations

import getpass
from pathlib import Path
from typing import Optional

import typer

from anchor.client import AnchorClient, AnchorClientError
from anchor.utils.output import err, out, success, warn


def push(
    path: str = typer.Argument(..., help="Secret path (e.g. myapp/db-password)"),
    value_opt: Optional[str] = typer.Option(
        None, "--value",
        help="[INSECURE] Plaintext value. Prefer interactive prompt or --file.",
        show_default=False,
    ),
    file: Optional[Path] = typer.Option(
        None, "--file", "-F", help="Read value from file"
    ),
    description: Optional[str] = typer.Option(
        None, "--desc", "-d", help="Human-readable description"
    ),
    users: Optional[str] = typer.Option(
        None, "--users", help="Comma-separated list of users that can read this secret"
    ),
    groups: Optional[str] = typer.Option(
        None, "--groups", help="Comma-separated list of groups that can read this secret"
    ),
    group_edit: bool = typer.Option(
        False, "--gedit", help="Allow group members to update this secret"
    ),
) -> None:
    """Create a new secret in the vault."""

    # ------------------------------------------------------------------
    # Resolve the secret value — priority: --file > interactive > --value
    # ------------------------------------------------------------------
    if file:
        value = file.read_text()

    elif value_opt is not None:
        warn(
            "Passing secrets via [bold]--value[/bold] exposes them in shell history "
            "and process listings. Use the interactive prompt or [bold]--file[/bold] instead."
        )
        value = value_opt

    else:
        # Interactive masked input — safest option
        try:
            value = getpass.getpass(f"Secret value for '{path}': ")
            confirm = getpass.getpass("Confirm value: ")
        except (EOFError, KeyboardInterrupt):
            err.print("\n[red]Aborted.[/red]")
            raise typer.Exit(1)
        if value != confirm:
            err.print("[red]✗ Values do not match.[/red]")
            raise typer.Exit(1)

    if not value:
        err.print("[red]✗ Secret value cannot be empty.[/red]")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # Build payload
    # ------------------------------------------------------------------
    payload: dict = {"plaintext": value}
    if description:
        payload["description"] = description
    if users:
        payload["allowed_users"] = [u.strip() for u in users.split(",") if u.strip()]
    if groups:
        payload["allowed_groups"] = [g.strip() for g in groups.split(",") if g.strip()]
    if group_edit:
        payload["group_edit"] = True

    # ------------------------------------------------------------------
    # Send to server
    # ------------------------------------------------------------------
    try:
        client = AnchorClient()
        resp = client.post(f"/vault/{path}", json=payload)
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if resp.status_code in (200, 201):
        success(f"Secret '{path}' created")
        return

    if resp.status_code == 409:
        err.print(
            f"[yellow]Secret '{path}' already exists.[/yellow] "
            f"Use [bold]anc secret update {path}[/bold] to create a new version."
        )
        raise typer.Exit(1)

    err.print(f"[red]✗ Failed ({resp.status_code}):[/red] {resp.text}")
    raise typer.Exit(1)
