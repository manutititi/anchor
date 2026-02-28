"""
anc pull — download anchor(s) from the server to local storage.

Examples:
    anc pull myproject              # pull a single anchor by name
    anc pull -f "type=ssh"          # pull all matching anchors
    anc pull --all --yes            # pull everything, no prompt
"""

from __future__ import annotations

from typing import Optional

import typer

from anchor.client import AnchorClient, AnchorClientError
from anchor.store import anchor_exists, save_anchor
from anchor.utils.output import err, info, out, success, warn


def pull(
    name: Optional[str] = typer.Argument(None, help="Anchor name to pull"),
    filter_str: Optional[str] = typer.Option(
        None, "--filter", "-f",
        help='Filter expression (e.g. "type=ssh AND meta.env=prod")',
    ),
    all_anchors: bool = typer.Option(
        False, "--all", help="Pull all anchors visible to the authenticated user",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip overwrite/confirmation prompts",
    ),
) -> None:
    """Pull anchor(s) from the server to local storage."""

    if not name and not filter_str and not all_anchors:
        err.print(
            "[yellow]Usage:[/yellow] anc pull <name>  |  -f <filter>  |  --all"
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
        _pull_one(client, name, yes=yes)
        return

    # ------------------------------------------------------------------
    # Batch: list from server, then pull each
    # ------------------------------------------------------------------
    params: dict = {}
    if filter_str:
        params["filter"] = filter_str

    try:
        resp = client.get("/anchors", params=params)
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if resp.status_code != 200:
        err.print(f"[red]✗ Failed to list anchors ({resp.status_code}):[/red] {resp.text}")
        raise typer.Exit(1)

    anchors: list[dict] = resp.json()
    if not anchors:
        warn("No anchors found matching criteria.")
        return

    out.print(f"[blue]{len(anchors)} anchor(s) matched:[/blue]")
    for a in anchors:
        out.print(f"  [cyan]⚓[/cyan] {a.get('name', '(unknown)')}")

    if not yes:
        confirmed = typer.confirm("Pull these anchors?", default=False)
        if not confirmed:
            out.print("[dim]Cancelled.[/dim]")
            return

    failures = 0
    for anchor_data in anchors:
        anchor_name = anchor_data.get("name")
        if not anchor_name:
            continue
        try:
            _pull_one(client, anchor_name, yes=True)
        except SystemExit:
            failures += 1

    if failures:
        err.print(f"[red]✗ {failures} anchor(s) failed to pull.[/red]")
        raise typer.Exit(1)
    success("All anchors pulled successfully.")


def _pull_one(client: AnchorClient, name: str, *, yes: bool) -> None:
    """Pull a single anchor; prompts for overwrite if it already exists."""
    if anchor_exists(name) and not yes:
        overwrite = typer.confirm(
            f"'{name}' already exists locally. Overwrite?", default=False
        )
        if not overwrite:
            info(f"Skipping '{name}'")
            return

    try:
        resp = client.get(f"/anchors/{name}")
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if resp.status_code == 404:
        err.print(f"[red]✗ Anchor '{name}' not found on server.[/red]")
        raise typer.Exit(1)

    if resp.status_code != 200:
        err.print(
            f"[red]✗ Failed to pull '{name}' ({resp.status_code}):[/red] {resp.text}"
        )
        raise typer.Exit(1)

    save_anchor(name, resp.json())
    success(f"'{name}' pulled")
