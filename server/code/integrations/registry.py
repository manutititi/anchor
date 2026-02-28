"""
Integration provider registry.

Providers are registered at import time. Adding a new integration
requires only: (1) implement IntegrationProvider, (2) register here.
"""
from typing import Optional
from integrations.base import IntegrationProvider

_registry: dict[str, IntegrationProvider] = {}


def register(provider: IntegrationProvider) -> None:
    _registry[provider.integration_type] = provider


def get_provider(integration_type: str) -> Optional[IntegrationProvider]:
    return _registry.get(integration_type)


def all_providers() -> dict[str, IntegrationProvider]:
    return dict(_registry)


# ---------------------------------------------------------------------------
# Built-in providers
# ---------------------------------------------------------------------------
from integrations.ldap.provider import LDAPProvider
from integrations.wireguard.provider import WireGuardProvider

register(LDAPProvider())
register(WireGuardProvider())
