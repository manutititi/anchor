"""Pydantic schemas for the WireGuard sidecar API."""

from pydantic import BaseModel, Field


class PeerCreate(BaseModel):
    """Payload for adding or updating a WireGuard peer."""

    pubkey: str = Field(..., description="WireGuard public key of the peer")
    allowed_ip: str = Field(
        ...,
        description="IP address to assign (without /32 — it is appended automatically)",
    )
    name: str = Field(..., description="Human-readable name for this peer")


class PeerInfo(BaseModel):
    """Full peer information returned by GET /peers."""

    name: str | None = None
    public_key: str
    endpoint: str | None = None
    allowed_ips: str
    latest_handshake: int = 0
    transfer_rx: int = 0
    transfer_tx: int = 0


class StatusResponse(BaseModel):
    """Response for GET /status healthcheck."""

    status: str
    interface: str
    public_key: str | None = None
    listen_port: int | None = None
    peer_count: int = 0


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    detail: str
