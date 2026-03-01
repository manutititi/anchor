"""
VPN endpoints — WireGuard lease management.

User endpoints (any authenticated user):
  POST   /vpn/request          — request a VPN lease (classic pool-based flow)
  POST   /vpn/promote          — promote an SPA onboarding lease to active
  GET    /vpn/status           — get own active lease
  DELETE /vpn/lease            — revoke own lease

Admin endpoints (admins group only):
  POST   /vpn/admin/users/{username}/otp   — generate OTP seed + assign vpn_uid
  DELETE /vpn/admin/users/{username}/otp   — revoke OTP seed + vpn_uid
  GET    /vpn/admin/leases                 — list all active leases
  DELETE /vpn/admin/leases/{uid}           — revoke any user's lease
  GET    /vpn/admin/pool                   — pool status (free/leased counts)
"""
import pyotp
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth.middleware import get_current_groups, get_current_user
from core.utils import now_tz
from db.client import get_collection
from vault.crypto import encrypt
from vpn.ip_pool import allocate_ip, free_ip, pool_status
from vpn.models import VPNRequestBody

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_admin(
    user: str = Depends(get_current_user),
    groups: list[str] = Depends(get_current_groups),
) -> str:
    if "admins" not in groups:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _get_provider():
    from integrations.wireguard.provider import WireGuardProvider
    return WireGuardProvider()


def _save_vault_secret(path: str, plaintext: str, uid: str) -> None:
    """Upsert a vault secret owned by uid (same schema as vault/router.py)."""
    col = get_collection("ref")
    encrypted = encrypt(plaintext, path)
    now = now_tz()
    existing = col.find_one({"id": path})
    if existing:
        col.update_one(
            {"id": path},
            {"$set": {
                "encrypted": encrypted,
                "last_updated": now,
                "version": existing.get("version", 1) + 1,
            }},
        )
    else:
        col.insert_one({
            "id": path,
            "encrypted": encrypted,
            "description": f"WireGuard VPN config for {uid}",
            "created_by": uid,
            "created_at": now,
            "last_updated": now,
            "version": 1,
            "groups": [],
            "users": [uid],
        })


def _do_revoke(lease: dict) -> None:
    """Best-effort: remove peer from sidecar, free IP, delete lease doc."""
    try:
        client = _get_provider().get_client()
        if client:
            client.remove_peer(lease["pubkey"])
    except Exception:
        pass  # sidecar failure must not block the DB cleanup

    free_ip(lease["assigned_ip"])
    get_collection("vpn_leases").delete_one({"uid": lease["uid"]})


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------

@router.post("/request", status_code=201, tags=["vpn"])
def request_vpn(
    body: VPNRequestBody,
    current_user: str = Depends(get_current_user),
):
    """
    Request a WireGuard VPN lease.
    Allocates an IP atomically, registers the peer on the sidecar,
    saves a partial wg config as a vault secret, and returns the config.
    """
    provider = _get_provider()
    if not provider.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="WireGuard integration is not configured or disabled",
        )

    leases_col = get_collection("vpn_leases")
    if leases_col.find_one({"uid": current_user}):
        raise HTTPException(
            status_code=409,
            detail="You already have an active VPN lease. Revoke it first with DELETE /vpn/lease.",
        )

    assigned_ip = allocate_ip(current_user)
    if not assigned_ip:
        raise HTTPException(status_code=503, detail="IP pool exhausted — no addresses available")

    client = provider.get_client()
    if not client:
        free_ip(assigned_ip)
        raise HTTPException(status_code=503, detail="Sidecar client unavailable")

    peer_name = body.peer_name or current_user

    try:
        client.add_peer(body.pubkey, assigned_ip, peer_name)
    except RuntimeError as exc:
        free_ip(assigned_ip)
        raise HTTPException(status_code=502, detail=f"Sidecar error: {exc}")

    # Fetch server public key from sidecar
    try:
        status = client.get_status()
        server_pubkey = status.get("public_key", "")
    except Exception:
        server_pubkey = ""

    server_endpoint = provider.get_server_endpoint()
    lease_hours = provider.get_lease_hours()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=lease_hours)
    vault_path = f"vpn/{current_user}"

    wg_conf = (
        f"[Interface]\n"
        f"Address = {assigned_ip}/32\n"
        f"DNS = 1.1.1.1\n"
        f"\n"
        f"[Peer]\n"
        f"PublicKey = {server_pubkey}\n"
        f"Endpoint = {server_endpoint}\n"
        f"AllowedIPs = 0.0.0.0/0\n"
        f"PersistentKeepalive = 25\n"
    )

    _save_vault_secret(vault_path, wg_conf, current_user)

    leases_col.insert_one({
        "uid": current_user,
        "pubkey": body.pubkey,
        "assigned_ip": assigned_ip,
        "peer_name": peer_name,
        "expires_at": expires_at.isoformat(),
        "created_at": now.isoformat(),
        "vault_path": vault_path,
    })

    return JSONResponse(status_code=201, content={
        "assigned_ip": assigned_ip,
        "server_pubkey": server_pubkey,
        "server_endpoint": server_endpoint,
        "lease_expires": expires_at.isoformat(),
        "vault_path": vault_path,
        "wg_conf_partial": wg_conf,
    })


@router.get("/status", tags=["vpn"])
def vpn_status(current_user: str = Depends(get_current_user)):
    """Return the caller's active VPN lease, or 404 if none."""
    lease = get_collection("vpn_leases").find_one({"uid": current_user}, {"_id": 0})
    if not lease:
        raise HTTPException(status_code=404, detail="No active VPN lease")
    return JSONResponse(content=lease)


@router.delete("/lease", tags=["vpn"])
def revoke_own_lease(current_user: str = Depends(get_current_user)):
    """Revoke the caller's own VPN lease."""
    lease = get_collection("vpn_leases").find_one({"uid": current_user})
    if not lease:
        raise HTTPException(status_code=404, detail="No active VPN lease to revoke")
    _do_revoke(lease)
    return JSONResponse(content={"detail": "VPN lease revoked"})


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/leases", tags=["vpn"])
def admin_list_leases(admin: str = Depends(_require_admin)):
    """List all active VPN leases."""
    leases = list(get_collection("vpn_leases").find({}, {"_id": 0}))
    return JSONResponse(content=leases)


@router.delete("/admin/leases/{uid}", tags=["vpn"])
def admin_revoke_lease(uid: str, admin: str = Depends(_require_admin)):
    """Admin: revoke any user's VPN lease."""
    lease = get_collection("vpn_leases").find_one({"uid": uid})
    if not lease:
        raise HTTPException(status_code=404, detail=f"No active VPN lease for '{uid}'")
    _do_revoke(lease)
    return JSONResponse(content={"detail": f"Lease for '{uid}' revoked"})


@router.get("/admin/pool", tags=["vpn"])
def admin_pool_status(admin: str = Depends(_require_admin)):
    """Admin: IP pool utilisation summary."""
    return JSONResponse(content=pool_status())


# ---------------------------------------------------------------------------
# SPA flow — OTP provisioning + promote
# ---------------------------------------------------------------------------

@router.post("/admin/users/{username}/otp", status_code=201, tags=["vpn"])
def admin_generate_otp(username: str, admin: str = Depends(_require_admin)):
    """
    Admin: generate a TOTP seed and assign a deterministic vpn_uid for username.
    The returned provisioning_url can be scanned as a QR code in any TOTP app.
    The seed_b32 is required for the CLI wizard (anc vpn up first-time setup).
    """
    user = get_collection("users").find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")

    from vpn.otp import assign_vpn_uid, generate_otp_seed
    vpn_uid = assign_vpn_uid(username)
    seed = generate_otp_seed(username)
    provisioning_url = pyotp.TOTP(seed).provisioning_uri(
        name=username, issuer_name="Anchor"
    )

    return JSONResponse(status_code=201, content={
        "vpn_uid": vpn_uid,
        "seed_b32": seed,
        "provisioning_url": provisioning_url,
    })


@router.delete("/admin/users/{username}/otp", tags=["vpn"])
def admin_revoke_otp(username: str, admin: str = Depends(_require_admin)):
    """Admin: revoke the OTP seed and vpn_uid for username."""
    get_collection("users").update_one(
        {"username": username},
        {"$unset": {"otp_seed_enc": "", "vpn_uid": "", "vpn_uid_assigned_at": ""}},
    )
    return JSONResponse(content={"detail": f"OTP and VPN UID revoked for '{username}'"})


@router.post("/promote", tags=["vpn"])
def promote_lease(current_user: str = Depends(get_current_user)):
    """
    Promote an onboarding VPN lease (created by the SPA knock flow) to active.

    Called by the client after authenticating through the restricted tunnel.
    Returns the full WireGuard config with AllowedIPs = 0.0.0.0/0 so the
    client can hot-reload the tunnel without bringing it down.
    """
    leases_col = get_collection("vpn_leases")
    lease = leases_col.find_one({"uid": current_user, "state": "onboarding"})
    if not lease:
        raise HTTPException(
            status_code=404,
            detail="No onboarding lease found. Run 'anc vpn up' first.",
        )

    provider = _get_provider()
    if not provider.is_enabled():
        raise HTTPException(status_code=503, detail="WireGuard not configured")

    client = provider.get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Sidecar unavailable")

    try:
        status = client.get_status()
        server_pubkey = status.get("public_key", "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sidecar error: {exc}")

    server_endpoint = provider.get_server_endpoint()
    lease_hours = provider.get_lease_hours()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=lease_hours)

    leases_col.update_one(
        {"uid": current_user},
        {"$set": {
            "state": "active",
            "expires_at": expires_at.isoformat(),
            "server_pubkey": server_pubkey,
        }},
    )

    wg_conf = (
        f"[Interface]\n"
        f"Address = {lease['assigned_ip']}/32\n"
        f"DNS = 1.1.1.1\n"
        f"\n"
        f"[Peer]\n"
        f"PublicKey = {server_pubkey}\n"
        f"Endpoint = {server_endpoint}\n"
        f"AllowedIPs = 0.0.0.0/0\n"
        f"PersistentKeepalive = 25\n"
    )

    return JSONResponse(content={
        "assigned_ip": lease["assigned_ip"],
        "server_pubkey": server_pubkey,
        "server_endpoint": server_endpoint,
        "lease_expires": expires_at.isoformat(),
        "wg_conf": wg_conf,
    })
