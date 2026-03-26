"""
Handler registry — one handler per anchor type.

Each handler implements:
    def handle(self, anchor: BaseAnchor, client: AnchorClient | None) -> None

To register a new handler from external code:
    from anchor.handlers import register
    register("mytype", MyHandler())
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anchor.client import AnchorClient
    from anchor.models.anchor import BaseAnchor


class Handler(ABC):
    @abstractmethod
    def handle(
        self,
        anchor: "BaseAnchor",
        client: "AnchorClient | None" = None,
    ) -> None: ...


_REGISTRY: dict[str, Handler] = {}


def register(anchor_type: str, handler: Handler) -> None:
    """Register a handler for the given anchor type."""
    _REGISTRY[anchor_type] = handler


def get_handler(anchor_type: str) -> Handler | None:
    """Return the handler for the given anchor type, or None if not registered."""
    return _REGISTRY.get(anchor_type)


def _setup() -> None:
    """Register all built-in handlers. Called once at import time."""
    from anchor.handlers.local import LocalHandler
    from anchor.handlers.ssh import SshHandler
    from anchor.handlers.url import UrlHandler

    register("local", LocalHandler())
    register("ssh", SshHandler())
    register("url", UrlHandler())


_setup()
