"""anc secret update — update an existing secret (creates a new version)."""

from __future__ import annotations

import getpass
from pathlib import Path
from typing import Optional

import typer

from anchor.client import AnchorClient, AnchorClientError
from anchor.utils.output import err, success, warn


def update(
    path: str = typer.Argument(..., help="Secret path (e.g. myapp/db-password)"),
    value_opt: Optional[str] = typer.Option(
        None, "--value",
        help="[INSECURE] New plaintext value. Prefer interactive prompt or --file.",
        show_default=False,
    ),
    file: Optional[Path] = typer.Option(
        None, "--file", "-F", help="Read new value from file"
    ),
    description: Optional[str] = typer.Option(
        None, "--desc", "-d", help="Update description"
    ),
    transfer_to: Optional[str] = typer.Option(
        None, "--transfer-to", help="Transfer ownership to another user (admin or creator only)"
    ),
) -> None:
    """Update an existing secret — a new version is created automatically."""

    # ------------------------------------------------------------------
    # Resolve new value
    # ------------------------------------------------------------------
    if file:
        value = file.read_text()

    elif value_opt is not None:
        warn(
            "Passing secrets via [bold]--value[/bold] exposes them in shell history "
            "and process listings."
        )
        value = value_opt

    else:
        try:
            value = getpass.getpass(f"New value for '{path}': ")
            confirm = getpass.getpass("Confirm: ")
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
    # Build payload — only include fields that were supplied
    # ------------------------------------------------------------------
    payload: dict = {"plaintext": value}
    if description is not None:
        payload["description"] = description
    if transfer_to:
        payload["transfer_to"] = transfer_to

    # ------------------------------------------------------------------
    # Send to server
    # ------------------------------------------------------------------
    try:
        client = AnchorClient()
        resp = client.put(f"/vault/{path}", json=payload)
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if resp.status_code == 200:
        success(f"Secret '{path}' updated (new version created)")
        return

    if resp.status_code == 404:
        err.print(
            f"[red]✗ Secret '{path}' not found.[/red] "
            f"Use [bold]anc secret push {path}[/bold] to create it."
        )
        raise typer.Exit(1)

    if resp.status_code == 403:
        err.print(f"[red]✗ Access denied for '{path}'.[/red]")
        raise typer.Exit(1)

    err.print(f"[red]✗ Failed ({resp.status_code}):[/red] {resp.text}")
    raise typer.Exit(1)
