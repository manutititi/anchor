"""
anc go <name>    — dispatch to the handler for the anchor's type.
anc _type <name> — print the anchor type to stdout (used by the shell wrapper).

The shell function in anchor/shell/anc.sh uses `anc _type` to decide
how to handle `anc <name>` without running the heavy dispatch twice for
interactive types like ssh.

Flow for `anc <name>` via shell wrapper:
    1. Shell calls `anc _type <name>` → prints e.g. "ssh"
    2. Shell routes:
       - local → `cd $(anc path <name>)`
       - ssh   → `anc go <name>`   (interactive, takes over terminal)
       - other → `anc go <name>`   (shows info or delegates)
"""

from __future__ import annotations

import subprocess
import typer

from anchor.client import AnchorClient, AnchorClientError, NotAuthenticatedError
from anchor.handlers import get_handler
from anchor.models.anchor import parse_anchor
from anchor.store import load_anchor
from anchor.utils.output import err, out
from anchor.utils.secrets import resolve_field


def go(
    name: str = typer.Argument(..., help="Anchor name"),
    pubkey: bool = typer.Option(False, "--pubkey", help="Mostrar la clave pública del anchor SSH"),
) -> None:
    """Dispatch to the appropriate handler based on the anchor's type."""
    try:
        data = load_anchor(name)
    except FileNotFoundError:
        err.print(f"[red]✗ Anchor '[bold]{name}[/bold]' not found.[/red]")
        raise typer.Exit(1)

    anchor = parse_anchor(data)
    client = _try_client()

    if pubkey:
        _show_pubkey(name, anchor, client)
        return

    handler = get_handler(anchor.type)

    if handler is None:
        err.print(
            f"[yellow]Anchor '[bold]{name}[/bold]' "
            f"(type=[bold]{anchor.type}[/bold]) — no handler registered.[/yellow]\n"
            f"  Run [bold]anc ls[/bold] to inspect it."
        )
        raise typer.Exit(1)

    try:
        handler.handle(anchor, client)
    except RuntimeError as exc:
        err.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(1)


def _show_pubkey(name: str, anchor, client: "AnchorClient | None") -> None:
    """Extrae y muestra la clave pública de un anchor SSH."""
    if anchor.type != "ssh":
        err.print(f"[red]✗ '{name}' no es un anchor SSH (tipo: {anchor.type}).[/red]")
        raise typer.Exit(1)

    raw_key = getattr(anchor, "key", None)
    if not raw_key:
        err.print(f"[red]✗ El anchor '{name}' no tiene clave configurada.[/red]")
        raise typer.Exit(1)

    try:
        key_str = resolve_field(raw_key, client)
    except RuntimeError as exc:
        err.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(1)

    if not key_str or not key_str.strip().startswith("-----BEGIN"):
        err.print("[red]✗ El valor de la clave no es un PEM válido.[/red]")
        raise typer.Exit(1)

    from anchor.handlers.ssh import _normalize_pem
    key_str = _normalize_pem(key_str)

    result = subprocess.run(
        ["ssh-keygen", "-y", "-f", "/dev/stdin"],
        input=key_str.encode(),
        capture_output=True,
    )
    if result.returncode != 0:
        err.print(
            f"[red]✗ No se pudo extraer la clave pública.[/red]\n"
            f"  {result.stderr.decode().strip()}"
        )
        raise typer.Exit(1)

    pubkey_line = result.stdout.decode().strip()
    out.print(f"\n[dim]Clave pública para[/dim] [bold]{name}[/bold] "
              f"[dim]({anchor.user}@{anchor.host}):[/dim]\n")
    print(pubkey_line)
    out.print(
        f"\n[dim]Añade esta línea a[/dim] [bold]~/.ssh/authorized_keys[/bold] "
        "[dim]en el servidor.[/dim]"
    )


def anchor_type(
    name: str = typer.Argument(..., help="Anchor name"),
) -> None:
    """Print the type of an anchor (used internally by the shell wrapper)."""
    try:
        data = load_anchor(name)
    except FileNotFoundError:
        raise typer.Exit(1)
    print(data.get("type", ""))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_client() -> AnchorClient | None:
    """Return an AnchorClient if server is configured and token is present.

    Returns None if the server is not configured or the user is not logged in.
    This allows offline use (anchors without [[secret:...]] markers work without
    a server).
    """
    try:
        return AnchorClient()
    except (AnchorClientError, NotAuthenticatedError):
        return None
