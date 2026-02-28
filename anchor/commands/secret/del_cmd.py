"""anc secret del — delete a secret from the vault."""

from __future__ import annotations

import typer

from anchor.client import AnchorClient, AnchorClientError
from anchor.utils.output import err, out, success


def del_secret(
    path: str = typer.Argument(..., help="Secret path to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a secret from the vault permanently."""

    if not yes:
        confirmed = typer.confirm(
            f"Permanently delete secret '{path}'?", default=False
        )
        if not confirmed:
            out.print("[dim]Cancelled.[/dim]")
            return

    try:
        client = AnchorClient()
        resp = client.delete(f"/vault/{path}")
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if resp.status_code == 200:
        success(f"Secret '{path}' deleted")
        return

    if resp.status_code == 404:
        err.print(f"[red]✗ Secret '{path}' not found.[/red]")
        raise typer.Exit(1)

    if resp.status_code == 403:
        err.print(f"[red]✗ Access denied for '{path}'.[/red]")
        raise typer.Exit(1)

    err.print(f"[red]✗ Failed ({resp.status_code}):[/red] {resp.text}")
    raise typer.Exit(1)
