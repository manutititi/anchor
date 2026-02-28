from abc import ABC, abstractmethod
from integrations.models import TestResult


class IntegrationProvider(ABC):
    """
    Base class for all external integration providers.

    Each provider encapsulates connectivity, authentication, and
    data-fetching logic for a specific external service (LDAP, SAML, OIDC…).
    Providers are registered in integrations/registry.py and can be
    configured at runtime via the /integrations API.
    """

    @property
    @abstractmethod
    def integration_type(self) -> str:
        """Unique lowercase identifier (e.g. 'ldap', 'saml')."""
        ...

    @abstractmethod
    def is_enabled(self) -> bool:
        """True if the provider is configured and marked as enabled."""
        ...

    @abstractmethod
    def test_connection(self) -> TestResult:
        """
        Probe the external service. Must not raise — return TestResult(ok=False)
        on any failure so callers get a structured error.
        """
        ...
