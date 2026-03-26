"""
anc ls — list anchors with optional filtering.

Examples:
    anc ls
    anc ls -f "type=ssh"
    anc ls -f "meta.env=prod AND type~ssh"
    anc ls -t url
    anc ls -r                    # list anchors on the server
    anc ls -r -f "type=ssh"     # filter server-side anchors
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.table import Table

from anchor.store import list_anchors
from anchor.utils.filter import parse_filter
from anchor.utils.output import err, out

# Map anchor type → Rich color
_TYPE_COLOR: dict[str, str] = {
    "local":    "bright_blue",
    "ssh":      "cyan",
    "url":      "magenta",
    "env":      "green",
    "files":    "yellow",
    "workflow": "white",
    "ansible":  "red",
    "docker":   "bright_cyan",
    "secret":   "bright_red",
    "ldap":     "bright_yellow",
}


def ls(
    filter_str: Optional[str] = typer.Option(
        None, "--filter", "-f",
        help='Filter expression (e.g. "type=ssh AND meta.env=prod")',
    ),
    type_filter: Optional[str] = typer.Option(
        None, "--type", "-t",
        help="Filter by anchor type (shorthand for -f type=<type>)",
    ),
    remote: bool = typer.Option(
        False, "--remote", "-r",
        help="List anchors from the server instead of local storage",
    ),
) -> None:
    """List anchors (local by default, or remote with -r)."""

    if remote:
        _ls_remote(filter_str, type_filter)
    else:
        _ls_local(filter_str, type_filter)


# ---------------------------------------------------------------------------
# Local listing
# ---------------------------------------------------------------------------

def _ls_local(filter_str: str | None, type_filter: str | None) -> None:
    filter_fn = None
    if filter_str:
        filter_fn = parse_filter(filter_str)
    elif type_filter:
        filter_fn = lambda d: d.get("type") == type_filter  # noqa: E731

    anchors = list_anchors(filter_fn)

    if not anchors:
        out.print("[dim]No anchors found.[/dim]")
        return

    _print_table([(name, data) for name, data in anchors])


# ---------------------------------------------------------------------------
# Remote listing
# ---------------------------------------------------------------------------

def _ls_remote(filter_str: str | None, type_filter: str | None) -> None:
    from anchor.client import AnchorClient, AnchorClientError

    try:
        client = AnchorClient()
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    params: dict = {}
    # Build server-side filter
    if filter_str:
        params["filter"] = filter_str
    elif type_filter:
        params["filter"] = f"type={type_filter}"

    try:
        resp = client.get("/anchors", params=params)
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if resp.status_code != 200:
        err.print(f"[red]✗ Server error ({resp.status_code}):[/red] {resp.text}")
        raise typer.Exit(1)

    anchors: list[dict] = resp.json()
    if not anchors:
        out.print("[dim]No remote anchors found.[/dim]")
        return

    out.print(f"[dim]server — {len(anchors)} anchor(s)[/dim]\n")
    _print_table([(a.get("name", "?"), a) for a in anchors])


# ---------------------------------------------------------------------------
# Shared table renderer
# ---------------------------------------------------------------------------

def _print_table(anchors: list[tuple[str, dict]]) -> None:
    table = Table(
        show_header=True,
        header_style="bold",
        show_lines=False,
        pad_edge=False,
        box=None,
    )
    table.add_column("Name", style="bold", min_width=12)
    table.add_column("Type", min_width=9)
    table.add_column("Location / Info")
    table.add_column("Groups", style="dim")
    table.add_column("Note", style="italic dim")

    for name, data in anchors:
        anchor_type = data.get("type", "?")
        color = _TYPE_COLOR.get(anchor_type, "white")
        type_cell = f"[{color}]{anchor_type}[/{color}]"

        location = _location(anchor_type, data)
        groups = ", ".join(data.get("groups", []))
        note = data.get("note") or ""

        table.add_row(name, type_cell, location, groups, note)

    out.print(table)


def _location(anchor_type: str, data: dict) -> str:
    """Return a human-readable location string for the given anchor type."""
    if anchor_type == "local":
        return data.get("path", "")
    if anchor_type == "ssh":
        user = data.get("user", "")
        host = data.get("host", "")
        port = data.get("port", 22)
        addr = f"{user}@{host}" if user else host
        return f"{addr}:{port}" if port != 22 else addr
    if anchor_type in ("url",):
        return data.get("base_url", "")
    if anchor_type == "env":
        return data.get("path", "")
    if anchor_type == "ldap":
        return data.get("host", "")
    return ""
