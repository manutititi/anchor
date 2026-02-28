"""
LocalHandler — handle 'local' type anchors.

Prints the expanded filesystem path to stdout.
The shell wrapper (anc function in anc.sh) captures this and executes: cd <path>
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from anchor.handlers import Handler
from anchor.utils.output import err

if TYPE_CHECKING:
    from anchor.client import AnchorClient
    from anchor.models.anchor import LocalAnchor


class LocalHandler(Handler):
    def handle(self, anchor: "LocalAnchor", client: "AnchorClient | None" = None) -> None:
        raw = getattr(anchor, "path", None)
        if not raw:
            err.print(f"[red]✗ Anchor '[bold]{anchor.name}[/bold]' has no path set.[/red]")
            raise SystemExit(1)
        print(os.path.expanduser(raw))
