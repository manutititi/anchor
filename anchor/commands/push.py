"""
anc push — upload local anchor(s) to the server.

Examples:
    anc push myproject              # push a single anchor
    anc push -f "meta.env=prod"     # push all prod anchors
    anc push -f "type=ssh" --yes    # no confirmation
"""

from __future__ import annotations

from typing import Optional

import typer

from anchor.client import AnchorClient, AnchorClientError
from anchor.store import list_anchors, load_anchor
from anchor.utils.filter import parse_filter
from anchor.utils.output import err, out, success, warn


def push(
    name: Optional[str] = typer.Argument(None, help="Anchor name to push"),
    filter_str: Optional[str] = typer.Option(
        None, "--filter", "-f",
        help='Filter expression (e.g. "meta.env=prod")',
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt",
    ),
) -> None:
    """Push local anchor(s) to the server."""

    if not name and not filter_str:
        err.print(
            "[yellow]Usage:[/yellow] anc push <name>  |  -f <filter>"
        )
        raise typer.Exit(1)

    try:
        client = AnchorClient()
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # Single anchor by name
    # ------------------------------------------------------------------
    if name:
        _push_one(client, name)
        return

    # ------------------------------------------------------------------
    # Batch: filter local anchors
    # ------------------------------------------------------------------
    filter_fn = parse_filter(filter_str) if filter_str else None
    matched = list_anchors(filter_fn)

    if not matched:
        warn("No local anchors matched the filter.")
        return

    out.print(f"[blue]{len(matched)} anchor(s) to push:[/blue]")
    for anchor_name, _ in matched:
        out.print(f"  [cyan]⚓[/cyan] {anchor_name}")

    if not yes:
        confirmed = typer.confirm("Push these anchors?", default=False)
        if not confirmed:
            out.print("[dim]Cancelled.[/dim]")
            return

    failures = 0
    for anchor_name, data in matched:
        try:
            _push_one(client, anchor_name, data=data)
        except SystemExit:
            failures += 1

    if failures:
        err.print(f"[red]✗ {failures} anchor(s) failed to push.[/red]")
        raise typer.Exit(1)
    success("All anchors pushed successfully.")


def _push_one(client: AnchorClient, name: str, *, data: dict | None = None) -> None:
    """Push a single anchor to the server."""
    if data is None:
        try:
            data = load_anchor(name)
        except FileNotFoundError:
            err.print(f"[red]✗ Anchor '{name}' not found locally.[/red]")
            raise typer.Exit(1)

    try:
        resp = client.post("/anchors", json=data)
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if resp.status_code in (200, 201):
        success(f"'{name}' pushed")
    else:
        err.print(
            f"[red]✗ Failed to push '{name}' ({resp.status_code}):[/red] {resp.text}"
        )
        raise typer.Exit(1)
