"""anc secret get — retrieve a secret value from the vault."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from anchor.client import AnchorClient, AnchorClientError
from anchor.utils.output import err, out, success


def get(
    path: str = typer.Argument(..., help="Secret path (e.g. myapp/db-password)"),
    version: Optional[int] = typer.Option(
        None, "--version", "-v", help="Specific version number to retrieve"
    ),
    out_file: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write value to file instead of printing to stdout"
    ),
) -> None:
    """Get a secret value from the vault."""

    try:
        client = AnchorClient()
        params: dict = {}
        if version is not None:
            params["version"] = version
        resp = client.get(f"/vault/{path}", params=params)
    except AnchorClientError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if resp.status_code == 404:
        err.print(f"[red]✗ Secret '{path}' not found.[/red]")
        raise typer.Exit(1)

    if resp.status_code == 403:
        err.print(f"[red]✗ Access denied for '{path}'.[/red]")
        raise typer.Exit(1)

    if resp.status_code != 200:
        err.print(f"[red]✗ Failed ({resp.status_code}):[/red] {resp.text}")
        raise typer.Exit(1)

    data = resp.json()
    value: str = data.get("plaintext", "")

    if out_file:
        out_file.write_text(value)
        # Restrict permissions on Unix
        import os, sys
        if sys.platform != "win32":
            os.chmod(out_file, 0o600)
        success(f"Secret saved to {out_file}")
    else:
        # Raw print — avoid Rich markup mangling special characters
        print(value, end="")
