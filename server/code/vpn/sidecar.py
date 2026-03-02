"""
HTTP client for the WireGuard sidecar API.

Uses urllib.request (stdlib) — no extra dependencies.
The sidecar exposes:
  POST   /peers           — add/update peer (requires X-API-Key)
  DELETE /peers/{pubkey}  — remove peer (requires X-API-Key)
  GET    /status          — interface healthcheck (no auth)
"""
import json
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import quote


class SidecarClient:
    def __init__(self, url: str, api_key: str = ""):
        self.url = url.rstrip("/")
        self.api_key = api_key

    def _headers(self, auth: bool = True) -> dict:
        h = {"Content-Type": "application/json"}
        if auth and self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        auth: bool = True,
    ) -> dict:
        url = f"{self.url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, headers=self._headers(auth), method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise RuntimeError(f"Sidecar HTTP {exc.code}: {body_text}")
        except Exception as exc:
            raise RuntimeError(f"Sidecar connection error: {exc}")

    def add_peer(self, pubkey: str, allowed_ip: str, name: str) -> dict:
        """Add or update a WireGuard peer on the sidecar. Returns sidecar response."""
        return self._request(
            "POST",
            "/peers",
            {"pubkey": pubkey, "allowed_ip": allowed_ip, "name": name},
        )

    def remove_peer(self, pubkey: str) -> None:
        """Remove a WireGuard peer from the sidecar."""
        # pubkey is base64 and may contain / and + — URL-encode it
        encoded = quote(pubkey, safe="")
        self._request("DELETE", f"/peers/{encoded}")

    def get_peers(self) -> list[dict]:
        """GET /peers — returns all peers with live stats (online, age_seconds, rx, tx)."""
        result = self._request("GET", "/peers")
        return result if isinstance(result, list) else []

    def get_status(self) -> dict:
        """GET /status — no auth required. Returns public_key, listen_port, peer_count."""
        return self._request("GET", "/status", auth=False)
