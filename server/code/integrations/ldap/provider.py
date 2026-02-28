"""
LDAP / Active Directory integration provider.

Config priority:
  1. MongoDB integrations collection (managed via API/UI)
  2. Environment variables (LDAP_SERVER, LDAP_BASE_DN, …) — bootstrap/fallback

Authentication strategy:
  - Passwords: always verified in real-time via LDAP bind (never cached)
  - Groups + attributes: fetched from LDAP on every login, synced to MongoDB users collection
"""
import logging
import ssl
import time
from typing import Optional

from ldap3 import ALL, SUBTREE, Connection, Server, Tls

from integrations.base import IntegrationProvider
from integrations.models import TestResult

logger = logging.getLogger(__name__)

ENCRYPTED_FIELDS = ["admin_password"]


class LDAPProvider(IntegrationProvider):

    @property
    def integration_type(self) -> str:
        return "ldap"

    # ------------------------------------------------------------------
    # Config resolution (DB → env var fallback)
    # ------------------------------------------------------------------

    def _get_config(self) -> Optional[dict]:
        from integrations.store import get_config
        from config import settings

        cfg = get_config("ldap")
        if cfg:
            return cfg

        # Bootstrap from environment variables if no DB config exists
        if settings.LDAP_SERVER:
            return {
                "server": settings.LDAP_SERVER,
                "base_dn": settings.LDAP_BASE_DN or "",
                "admin_dn": settings.LDAP_ADMIN_DN or "",
                "admin_password": settings.LDAP_ADMIN_PASSWORD or "",
                "user_search_base": "ou=users",
                "group_search_base": "ou=groups",
                "uid_attribute": "uid",
                "tls_verify": True,
                "timeout": 5,
                "enabled": settings.LDAP_AUTH_ENABLED,
                "sync_attributes": ["mail", "displayName", "cn"],
            }

        return None

    # ------------------------------------------------------------------
    # IntegrationProvider interface
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        cfg = self._get_config()
        return bool(cfg and cfg.get("enabled", True) and cfg.get("server"))

    def test_connection(self) -> TestResult:
        cfg = self._get_config()
        if not cfg:
            return TestResult(ok=False, error="No LDAP configuration found")
        if not cfg.get("enabled", True):
            return TestResult(ok=False, error="LDAP integration is disabled")

        start = time.monotonic()
        try:
            server, conn = self._admin_bind(cfg)
            latency_ms = round((time.monotonic() - start) * 1000, 2)

            # Verify we can search the base DN
            conn.search(
                search_base=cfg["base_dn"],
                search_filter="(objectClass=*)",
                search_scope="BASE",
                attributes=["*"],
            )

            details: dict = {"server": cfg["server"], "base_dn": cfg["base_dn"]}
            if server.info:
                if server.info.vendor_name:
                    details["vendor"] = str(server.info.vendor_name)
                if server.info.vendor_version:
                    details["version"] = str(server.info.vendor_version)
                if server.info.naming_contexts:
                    details["naming_contexts"] = [str(nc) for nc in server.info.naming_contexts]

            conn.unbind()
            return TestResult(ok=True, latency_ms=latency_ms, details=details)

        except Exception as exc:
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return TestResult(ok=False, latency_ms=latency_ms, error=str(exc))

    # ------------------------------------------------------------------
    # Auth methods (called by auth/ldap.py)
    # ------------------------------------------------------------------

    def authenticate(self, username: str, password: str) -> bool:
        cfg = self._get_config()
        if not cfg:
            return False
        user_dn = self._get_user_dn(username, cfg)
        if not user_dn:
            logger.warning("LDAP user not found: %s", username)
            return False
        try:
            server = self._build_server(cfg)
            Connection(server, user=user_dn, password=password, auto_bind=True)
            return True
        except Exception as exc:
            logger.warning("LDAP auth failed for %s: %s", username, exc)
            return False

    def get_groups(self, username: str) -> list[str]:
        """
        Return group cn values for a user.

        Handles both common LDAP group schemas:
          - groupOfNames  → member attribute holds the full user DN
          - posixGroup    → memberUid attribute holds just the uid string
        Uses a compound OR filter so a single search covers both.
        """
        cfg = self._get_config()
        if not cfg:
            return []
        user_dn = self._get_user_dn(username, cfg)
        if not user_dn:
            return []
        try:
            _, conn = self._admin_bind(cfg)
            conn.search(
                search_base=self._search_base(cfg, cfg.get("group_search_base", "ou=groups")),
                search_filter=f"(|(member={user_dn})(memberUid={username}))",
                search_scope=SUBTREE,
                attributes=["cn"],
            )
            return [entry.cn.value for entry in conn.entries]
        except Exception as exc:
            logger.warning("LDAP get_groups failed for %s: %s", username, exc)
            return []

    def get_user_attributes(self, username: str) -> dict:
        """Fetch user profile attributes for on-login sync."""
        cfg = self._get_config()
        if not cfg:
            return {}
        user_dn = self._get_user_dn(username, cfg)
        if not user_dn:
            return {}
        sync_attrs = cfg.get("sync_attributes", ["mail", "displayName", "cn"])
        try:
            _, conn = self._admin_bind(cfg)
            conn.search(
                search_base=user_dn,
                search_filter="(objectClass=*)",
                search_scope="BASE",
                attributes=sync_attrs,
            )
            if not conn.entries:
                return {}
            entry = conn.entries[0]
            result = {}
            for attr in sync_attrs:
                val = getattr(entry, attr, None)
                if val and val.value:
                    result[attr] = val.value
            return result
        except Exception as exc:
            logger.warning("LDAP get_user_attributes failed for %s: %s", username, exc)
            return {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_server(self, cfg: dict) -> Server:
        use_ssl = cfg["server"].startswith("ldaps://")
        tls = None
        if use_ssl and not cfg.get("tls_verify", True):
            tls = Tls(validate=ssl.CERT_NONE)
        return Server(
            cfg["server"],
            get_info=ALL,
            use_ssl=use_ssl,
            tls=tls,
            connect_timeout=cfg.get("timeout", 5),
        )

    def _admin_bind(self, cfg: dict) -> tuple[Server, Connection]:
        server = self._build_server(cfg)
        conn = Connection(
            server,
            user=cfg["admin_dn"],
            password=cfg["admin_password"],
            auto_bind=True,
        )
        return server, conn

    def _search_base(self, cfg: dict, relative: str) -> str:
        """Build absolute search base.
        If relative already contains the base_dn, use it as-is.
        Otherwise, append base_dn (e.g. 'ou=users' → 'ou=users,dc=company,dc=com').
        """
        base = cfg["base_dn"]
        rel = relative.strip()
        if not rel:
            return base
        if rel.endswith(base):
            return rel
        return f"{rel},{base}"

    def _get_user_dn(self, username: str, cfg: dict) -> Optional[str]:
        uid_attr = cfg.get("uid_attribute", "uid")
        try:
            _, conn = self._admin_bind(cfg)
            conn.search(
                search_base=self._search_base(cfg, cfg.get("user_search_base", "ou=users")),
                search_filter=f"({uid_attr}={username})",
                search_scope=SUBTREE,
                attributes=[uid_attr],
            )
            if conn.entries:
                return conn.entries[0].entry_dn
        except Exception as exc:
            logger.warning("LDAP get_user_dn failed for %s: %s", username, exc)
        return None
