"""
anc path <name> — print the filesystem path for a local anchor.

Designed for shell integration:
    cd $(anc path myproject)

Or add to .bashrc:
    goto() { cd "$(anc path "$1")"; }
"""

from __future__ import annotations

import os

import typer

from anchor.store import load_anchor
from anchor.utils.output import err


def path(
    name: str = typer.Argument(..., help="Anchor name"),
) -> None:
    """Print the filesystem path of a local anchor (for use with cd)."""

    try:
        data = load_anchor(name)
    except FileNotFoundError:
        err.print(f"[red]✗ Anchor '{name}' not found.[/red]")
        raise typer.Exit(1)

    anchor_type = data.get("type")

    if anchor_type == "local":
        raw = data.get("path")
        if not raw:
            err.print(f"[red]✗ Anchor '{name}' has no path set.[/red]")
            raise typer.Exit(1)
        # Expand ~ so the shell receives an absolute path
        print(os.path.expanduser(raw))

    elif anchor_type == "ssh":
        host = data.get("host", "")
        user = data.get("user", "")
        addr = f"{user}@{host}" if user else host
        err.print(
            f"[yellow]'{name}' is an SSH anchor ({addr}).[/yellow] "
            "Use [bold]anc ssh {name}[/bold] to connect."
        )
        raise typer.Exit(1)

    else:
        err.print(
            f"[red]✗ Anchor '{name}' (type={anchor_type!r}) has no navigable path.[/red]"
        )
        raise typer.Exit(1)
