"""anc secret ls — list secrets visible to the authenticated user."""

from __future__ import annotations

from typing import Optional

import typer
from rich import box
from rich.table import Table

from anchor.client import AnchorClient, AnchorClientError
from anchor.utils.output import err, out


def ls(
    prefix: Optional[str] = typer.Argument(
        None, help="Path prefix to filter (e.g. myapp/)"
    ),
) -> None:
    """List secrets in the vault."""

    try:
        client = AnchorClient()
        params: dict = {}
        if prefix:
            params["prefix"] = prefix
        resp = client.get("/vault", params=params)
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if resp.status_code != 200:
        err.print(f"[red]✗ Failed ({resp.status_code}):[/red] {resp.text}")
        raise typer.Exit(1)

    secrets: list[dict] = resp.json()
    if not secrets:
        out.print("[dim]No secrets found.[/dim]")
        return

    table = Table(
        show_header=True,
        header_style="bold",
        box=box.SIMPLE_HEAD,
        pad_edge=True,
        show_lines=False,
    )
    table.add_column("Path", style="cyan", min_width=20, no_wrap=True)
    table.add_column("Description", min_width=16)
    table.add_column("Owner", min_width=10)
    table.add_column("Ver", justify="right", min_width=4)
    table.add_column("Updated", min_width=19)

    for s in secrets:
        updated = _fmt_date(s.get("last_updated", ""))
        table.add_row(
            s.get("id", ""),
            s.get("description", "") or "",
            s.get("created_by", "") or "",
            str(s.get("version", 1)),
            updated,
        )

    out.print(table)


def _fmt_date(iso: str) -> str:
    """Trim ISO timestamp to 'YYYY-MM-DD HH:MM' for compact display."""
    if not iso:
        return ""
    # e.g. "2026-02-27T15:30:00+00:00" → "2026-02-27 15:30"
    return iso[:16].replace("T", " ")
