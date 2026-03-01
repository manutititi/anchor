"""
WireGuard VPN integration provider.

Config is stored in the integrations MongoDB collection (type='wireguard').
Sensitive field: api_key (encrypted with AES-256-GCM+HKDF).
"""
import time
from typing import Optional

from integrations.base import IntegrationProvider
from integrations.models import TestResult


class WireGuardProvider(IntegrationProvider):

    @property
    def integration_type(self) -> str:
        return "wireguard"

    def _get_config(self) -> Optional[dict]:
        from integrations.store import get_config
        return get_config("wireguard")

    # ------------------------------------------------------------------
    # IntegrationProvider interface
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        cfg = self._get_config()
        return bool(cfg and cfg.get("enabled") and cfg.get("sidecar_url"))

    def test_connection(self) -> TestResult:
        cfg = self._get_config()
        if not cfg:
            return TestResult(ok=False, error="No WireGuard configuration found")
        if not cfg.get("enabled"):
            return TestResult(ok=False, error="WireGuard integration is disabled")

        start = time.monotonic()
        try:
            from vpn.sidecar import SidecarClient
            client = SidecarClient(cfg["sidecar_url"], cfg.get("api_key", ""))
            status = client.get_status()
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return TestResult(
                ok=True,
                latency_ms=latency_ms,
                details={
                    "interface": status.get("interface", "wg0"),
                    "public_key": status.get("public_key", ""),
                    "listen_port": status.get("listen_port", 0),
                    "peer_count": status.get("peer_count", 0),
                },
            )
        except Exception as exc:
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return TestResult(ok=False, latency_ms=latency_ms, error=str(exc))

    # ------------------------------------------------------------------
    # VPN-specific helpers (used by vpn/router.py and janitor.py)
    # ------------------------------------------------------------------

    def get_client(self):
        """Return a SidecarClient, or None if not configured."""
        cfg = self._get_config()
        if not cfg or not cfg.get("sidecar_url"):
            return None
        from vpn.sidecar import SidecarClient
        return SidecarClient(cfg["sidecar_url"], cfg.get("api_key", ""))

    def get_server_endpoint(self) -> str:
        cfg = self._get_config()
        return cfg.get("server_endpoint", "") if cfg else ""

    def get_lease_hours(self) -> int:
        cfg = self._get_config()
        return int(cfg.get("lease_hours", 8)) if cfg else 8

    def get_subnet(self) -> str:
        cfg = self._get_config()
        return cfg.get("subnet", "10.13.13.0/24") if cfg else "10.13.13.0/24"

    def get_routes(self) -> list[str]:
        cfg = self._get_config()
        return list(cfg.get("routes", ["0.0.0.0/0"])) if cfg else ["0.0.0.0/0"]
