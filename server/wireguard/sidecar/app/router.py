"""
API router — WireGuard peer management endpoints.

POST   /peers          → Add or update a peer (zero downtime)
GET    /peers          → List all peers with metadata
DELETE /peers/{pubkey}  → Remove a peer
GET    /status         → Healthcheck (interface exists + permissions)
"""

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models import PeerCreate, PeerInfo, StatusResponse, ErrorResponse
from app.wg import add_peer, remove_peer, show_dump, check_interface, WireGuardError
from app import peers as meta

router = APIRouter()


@router.post(
    "/peers",
    response_model=dict,
    responses={500: {"model": ErrorResponse}},
    tags=["peers"],
    summary="Add or update a WireGuard peer",
)
def create_or_update_peer(body: PeerCreate):
    """
    Execute `wg set wg0 peer <pubkey> allowed-ips <ip>/32` (zero downtime)
    and persist the human-readable name in the local metadata file.
    """
    try:
        add_peer(body.pubkey, body.allowed_ip)
    except WireGuardError as exc:
        raise HTTPException(status_code=500, detail=exc.stderr)

    meta.set_peer(body.pubkey, body.name)

    return JSONResponse(
        status_code=200,
        content={
            "detail": f"Peer '{body.name}' ({body.pubkey[:8]}…) configured with allowed IP {body.allowed_ip}/32",
        },
    )


@router.get(
    "/peers",
    response_model=list[PeerInfo],
    responses={500: {"model": ErrorResponse}},
    tags=["peers"],
    summary="List all WireGuard peers",
)
def list_peers():
    """
    Execute `wg show wg0 dump`, parse the output, and cross-reference
    with the local metadata file to enrich each peer with its name.
    """
    try:
        dump = show_dump()
    except WireGuardError as exc:
        raise HTTPException(status_code=500, detail=exc.stderr)

    metadata = meta.load_metadata()
    result: list[dict] = []

    for peer in dump.peers:
        name = None
        entry = metadata.get(peer.public_key)
        if isinstance(entry, dict):
            name = entry.get("name")

        result.append(
            PeerInfo(
                name=name,
                public_key=peer.public_key,
                endpoint=peer.endpoint,
                allowed_ips=peer.allowed_ips,
                latest_handshake=peer.latest_handshake,
                transfer_rx=peer.transfer_rx,
                transfer_tx=peer.transfer_tx,
            ).model_dump()
        )

    return JSONResponse(content=result)


@router.delete(
    "/peers/{pubkey:path}",
    response_model=dict,
    responses={500: {"model": ErrorResponse}},
    tags=["peers"],
    summary="Remove a WireGuard peer",
)
def delete_peer(pubkey: str):
    """
    Remove a peer from the live interface and clean up metadata.
    The pubkey is URL-encoded in the path (base64 contains `/` and `+`).
    """
    pubkey = unquote(pubkey)

    try:
        remove_peer(pubkey)
    except WireGuardError as exc:
        raise HTTPException(status_code=500, detail=exc.stderr)

    meta.delete_peer(pubkey)

    return JSONResponse(
        content={"detail": f"Peer {pubkey[:8]}… removed"},
    )


@router.get(
    "/status",
    response_model=StatusResponse,
    responses={500: {"model": ErrorResponse}},
    tags=["health"],
    summary="WireGuard interface healthcheck",
)
def status():
    """
    Verify that the wg0 interface exists and the process has
    sufficient permissions to query it.
    """
    try:
        info = check_interface()
    except WireGuardError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Interface check failed: {exc.stderr}",
        )

    return JSONResponse(
        content={
            "status": "healthy",
            "interface": "wg0",
            "public_key": info.get("public_key"),
            "listen_port": info.get("listen_port"),
            "peer_count": info.get("peer_count", 0),
        },
    )
