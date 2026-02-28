"""
AnchorClient — authenticated HTTP client for the Anchor server.

Usage:
    client = AnchorClient()
    resp = client.get("/anchors")
    resp = client.post("/vault/myapp/secret", json={"value": "..."})
"""

from __future__ import annotations

from typing import Any

import requests
from requests import Response

from anchor.config import get_server_url, get_token

DEFAULT_TIMEOUT = 10  # seconds


class AnchorClientError(Exception):
    """Raised for connection errors, timeouts, or missing config."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class NotAuthenticatedError(AnchorClientError):
    """Raised when no valid token is available."""


class AnchorClient:
    """Thin wrapper around requests that injects auth headers and a base URL."""

    def __init__(
        self,
        server_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self._server_url = server_url or get_server_url()
        self._token = token or get_token()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        if not self._server_url:
            raise AnchorClientError(
                "Server not configured. Run: anc login --url <server-url>"
            )
        return self._server_url.rstrip("/")

    @property
    def token(self) -> str:
        if not self._token:
            raise NotAuthenticatedError(
                "Not authenticated. Run: anc login"
            )
        return self._token

    # ------------------------------------------------------------------
    # HTTP methods
    # ------------------------------------------------------------------

    def get(self, path: str, **kwargs: Any) -> Response:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Response:
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Response:
        return self._request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Response:
        return self._request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Response:
        return self._request("DELETE", path, **kwargs)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _url_for(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)

        # Merge auth headers with any caller-supplied headers
        caller_headers = kwargs.pop("headers", {})
        kwargs["headers"] = {**self._auth_headers(), **caller_headers}

        url = self._url_for(path)
        try:
            return requests.request(method, url, **kwargs)
        except requests.exceptions.ConnectionError:
            raise AnchorClientError(f"Cannot connect to server at {self.base_url}")
        except requests.exceptions.Timeout:
            raise AnchorClientError(f"Request timed out: {url}")
        except requests.exceptions.RequestException as exc:
            raise AnchorClientError(f"Request failed: {exc}")
