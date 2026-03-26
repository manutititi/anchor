"""
UrlHandler — handle 'url' type anchors.

Opens the anchor's base_url in the default web browser.
"""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from anchor.handlers import Handler
from anchor.utils.output import err, out

if TYPE_CHECKING:
    from anchor.client import AnchorClient
    from anchor.models.anchor import UrlAnchor


class UrlHandler(Handler):
    def handle(self, anchor: "UrlAnchor", client: "AnchorClient | None" = None) -> None:
        url = getattr(anchor, "base_url", None)
        if not url:
            err.print(f"[red]✗ Anchor '[bold]{anchor.name}[/bold]' has no base_url set.[/red]")
            raise SystemExit(1)
        out.print(f"[dim]Opening[/dim] [bold]{url}[/bold]")
        webbrowser.open(url)
