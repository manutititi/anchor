"""
VPN endpoints — WireGuard lease management.

User endpoints (any authenticated user):
  POST   /vpn/request          — request a VPN lease (classic pool-based flow)
  POST   /vpn/promote          — promote an SPA onboarding lease to active
  GET    /vpn/status           — get own active lease
  DELETE /vpn/lease            — revoke own lease

Admin endpoints (admins group only):
  POST   /vpn/admin/users/{username}/otp      — generate OTP seed + assign vpn_uid
  DELETE /vpn/admin/users/{username}/otp      — revoke OTP seed + vpn_uid
  PATCH  /vpn/admin/users/{username}/settings — per-user lease duration + blackout window
  GET    /vpn/admin/leases                    — list all active leases
  DELETE /vpn/admin/leases/{uid}              — revoke any user's lease
  GET    /vpn/admin/pool                      — pool status (free/leased counts)
"""
import base64
import json
import pyotp
from datetime import datetime, timedelta, timezone

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth.middleware import get_current_groups, get_current_user
from config import settings
from core.logger import LogEntry
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


def _save_vault_secret(path: str, plaintext: str, uid: str, description: str = "", owner: str | None = None) -> None:
    """Upsert a vault secret using the same flat schema as vault/router.py.

    uid   — actor recorded in updated_by (the admin performing the action).
    owner — user who owns the secret (created_by + users[]); defaults to uid.
    """
    actual_owner = owner or uid
    col = get_collection("ref")
    encrypted = encrypt(plaintext, path)
    now = now_tz()
    existing = col.find_one({"id": path})
    if existing:
        col.update_one(
            {"id": path},
            {"$set": {
                "value": encrypted["value"],
                "iv": encrypted["iv"],
                "tag": encrypted["tag"],
                "encoding": encrypted["encoding"],
                "last_updated": now,
                "updated_by": uid,
                "version": existing.get("version", 1) + 1,
                "created_by": actual_owner,
                "users": [actual_owner],
            }},
        )
    else:
        col.insert_one({
            "type": "secret",
            "id": path,
            "description": description or f"WireGuard VPN config for {actual_owner}",
            "encoding": encrypted["encoding"],
            "value": encrypted["value"],
            "iv": encrypted["iv"],
            "tag": encrypted["tag"],
            "version": 1,
            "created_at": now,
            "last_updated": now,
            "created_by": actual_owner,
            "updated_by": uid,
            "users": [actual_owner],
            "groups": [],
            "allow_group_edit": False,
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


def _make_expires_at(lease_seconds: int | None) -> str | None:
    """
    Return an ISO-format UTC datetime for the given duration, or None for infinite.
    """
    if lease_seconds is None:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------

@router.post("/request", status_code=201, tags=["vpn"])
def request_vpn(
    body: VPNRequestBody,
    request: Request,
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
    user_doc = get_collection("users").find_one({"username": current_user}) or {}
    lease_secs = provider.get_effective_lease_seconds(user_doc)
    now = datetime.now(timezone.utc)
    expires_at_iso = _make_expires_at(lease_secs)
    vault_path = f"vpn/{current_user}"

    dns_servers = provider.get_dns()
    dns_line = f"DNS = {', '.join(dns_servers)}\n" if dns_servers else ""
    wg_conf = (
        f"[Interface]\n"
        f"Address = {assigned_ip}/32\n"
        f"{dns_line}"
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
        "expires_at": expires_at_iso,
        "created_at": now.isoformat(),
        "vault_path": vault_path,
    })

    response = JSONResponse(status_code=201, content={
        "assigned_ip": assigned_ip,
        "server_pubkey": server_pubkey,
        "server_endpoint": server_endpoint,
        "lease_expires": expires_at_iso,
        "vault_path": vault_path,
        "wg_conf_partial": wg_conf,
    })
    LogEntry.from_request(
        request=request, response=response,
        resource="secret", resource_id=vault_path,
        action="create", success=True,
        extra={"context": "vpn_request", "assigned_ip": assigned_ip},
    ).save_default()
    LogEntry.from_request(
        request=request, response=response,
        resource="vpn_lease", resource_id=current_user,
        action="grant", success=True,
        extra={
            "assigned_ip": assigned_ip,
            "lease_hours": lease_hours,
            "expires_at": expires_at.isoformat(),
        },
    ).save_default()
    return response


@router.get("/status", tags=["vpn"])
def vpn_status(current_user: str = Depends(get_current_user)):
    """Return the caller's active VPN lease, or 404 if none."""
    lease = get_collection("vpn_leases").find_one({"uid": current_user}, {"_id": 0})
    if not lease:
        raise HTTPException(status_code=404, detail="No active VPN lease")
    return JSONResponse(content=lease)


@router.get("/sync", tags=["vpn"])
def vpn_sync(current_user: str = Depends(get_current_user)):
    """
    Return current routes and endpoint info for the caller's active VPN lease.
    Clients can call this to refresh AllowedIPs without going through the full
    promote flow (e.g. after admin changes the routed networks in the UI).
    """
    lease = get_collection("vpn_leases").find_one(
        {"uid": current_user, "state": "active"}, {"_id": 0}
    )
    if not lease:
        raise HTTPException(status_code=404, detail="No active VPN lease")

    provider = _get_provider()
    routes = provider.get_routes()
    return JSONResponse(content={
        "assigned_ip": lease["assigned_ip"],
        "routes": routes,
        "server_pubkey": lease.get("server_pubkey", ""),
        "server_endpoint": provider.get_server_endpoint(),
        "lease_expires": lease.get("expires_at", ""),
    })


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

@router.get("/admin/peers", tags=["vpn"])
def admin_list_live_peers(admin: str = Depends(_require_admin)):
    """
    Admin: live peer stats from the sidecar, enriched with MongoDB lease state.
    Returns each peer's online status, handshake age, rx/tx, and lease metadata.
    """
    provider = _get_provider()
    if not provider.is_enabled():
        raise HTTPException(status_code=503, detail="WireGuard integration not configured or disabled")

    sidecar = provider.get_client()
    if not sidecar:
        raise HTTPException(status_code=503, detail="Sidecar unavailable")

    try:
        peers = sidecar.get_peers()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    lease_map = {
        l["uid"]: l
        for l in get_collection("vpn_leases").find({}, {"_id": 0})
    }

    result = []
    for peer in peers:
        name = peer.get("name") or ""
        lease = lease_map.get(name, {})
        result.append({
            **peer,
            "state": lease.get("state"),
            "expires_at": lease.get("expires_at"),
        })
    return JSONResponse(content=result)


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

def _get_wg_context(provider, admin_username: str) -> tuple[dict, str, str, str, int, str]:
    """
    Shared helper: validate sidecar, get server pubkey, parse config fields.
    Returns: (wg_cfg, server_pubkey, server_endpoint, subnet, knock_port, knock_host)
    """
    if not provider.is_enabled():
        raise HTTPException(status_code=503, detail="WireGuard integration not configured or disabled")

    sidecar = provider.get_client()
    if not sidecar:
        raise HTTPException(status_code=503, detail="WireGuard sidecar unavailable")
    try:
        status = sidecar.get_status()
        server_pubkey: str = status.get("public_key", "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sidecar unreachable: {exc}")

    wg_cfg = provider._get_config() or {}
    server_endpoint: str = wg_cfg.get("server_endpoint", "")
    if server_endpoint and ":" not in server_endpoint:
        server_endpoint = f"{server_endpoint}:51820"
    knock_host = server_endpoint.split(":")[0] if ":" in server_endpoint else server_endpoint
    subnet: str = wg_cfg.get("subnet", "10.13.13.0/24")
    knock_port: int = settings.VPN_KNOCK_PORT or int(wg_cfg.get("knock_port", 0) or 0)

    return wg_cfg, server_pubkey, server_endpoint, subnet, knock_port, knock_host


@router.post("/admin/users/{username}/otp", status_code=201, tags=["vpn"])
def admin_provision_otp(username: str, request: Request, admin: str = Depends(_require_admin)):
    """
    Admin: provision TOTP seed for knock-based VPN access (default flow).

    Generates a TOTP seed + assigns a vpn_uid. Does NOT pre-generate a WG keypair
    or register a sidecar peer. The user's first 'anc vpn up' does the peer
    registration via SPA knock → onboarding tunnel → promote.

    The provision_token contains only public data (no secrets). The user saves it
    with 'anc vpn init <token>' and scans the QR from 'provisioning_url' into
    their authenticator app.

    Returns:
    - provisioning_url: otpauth:// URI — display to user (QR in admin UI)
    - provision_token:  base64url JSON — paste into 'anc vpn init <token>'
    """
    import traceback
    try:
        user = get_collection("users").find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")

        provider = _get_provider()
        wg_cfg, server_pubkey, server_endpoint, subnet, knock_port, knock_host = \
            _get_wg_context(provider, admin)
        server_vpn_uid: int = int(wg_cfg.get("server_vpn_uid", 1) or 1)

        from vpn.otp import assign_vpn_uid, generate_otp_seed
        vpn_uid = assign_vpn_uid(username)
        seed = generate_otp_seed(username)
        provisioning_url = pyotp.TOTP(seed).provisioning_uri(name=username, issuer_name="Anchor")

        # SPA public key — included in token so client can build SPA v2 packets
        from vpn.spa import get_spa_pubkey_b64
        spa_pubkey = get_spa_pubkey_b64()
        if not spa_pubkey:
            raise HTTPException(status_code=503, detail="SPA keypair not initialized on server")

        token_payload = {
            "uid": username,
            "vpn_uid": vpn_uid,
            "knock_host": knock_host,
            "knock_port": knock_port,
            "subnet": subnet,
            "server_vpn_uid": server_vpn_uid,
            "server_endpoint": server_endpoint,
            "server_pubkey": server_pubkey,
            "server_port": settings.VPN_SERVER_PORT,
            "spa_pubkey": spa_pubkey,
        }
        provision_token = base64.urlsafe_b64encode(
            json.dumps(token_payload).encode()
        ).decode()

        response = JSONResponse(status_code=201, content={
            "vpn_uid": vpn_uid,
            "provisioning_url": provisioning_url,
            "provision_token": provision_token,
        })
        LogEntry.from_request(
            request=request, response=response,
            resource="vpn_otp", resource_id=username,
            action="create", success=True,
            extra={"context": "vpn_admin_otp", "provisioned_for": username, "vpn_uid": vpn_uid},
        ).save_default()
        return response

    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/admin/users/{username}/provision", status_code=201, tags=["vpn"])
def admin_provision_full(username: str, request: Request, admin: str = Depends(_require_admin)):
    """
    Admin: full pre-provisioned WireGuard peer (legacy / machine flow).

    Generates a WireGuard keypair server-side, registers the peer on the
    sidecar, creates an active lease, and saves the full wg.conf (with PrivateKey)
    as a vault secret (vpn/{username}).

    The provision_token contains WG private key + TOTP seed — share securely.
    Use this for automated machines or when the user cannot do the TOTP setup.

    For the standard interactive user flow, use POST /admin/users/{username}/otp instead.
    """
    import traceback

    try:
        user = get_collection("users").find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")

        provider = _get_provider()
        wg_cfg, server_pubkey, server_endpoint, subnet, knock_port, knock_host = \
            _get_wg_context(provider, admin)
        sidecar = provider.get_client()
        server_vpn_uid: int = int(wg_cfg.get("server_vpn_uid", 1) or 1)

        from vpn.otp import assign_vpn_uid, generate_otp_seed
        vpn_uid = assign_vpn_uid(username)
        seed = generate_otp_seed(username)
        provisioning_url = pyotp.TOTP(seed).provisioning_uri(name=username, issuer_name="Anchor")

        from vpn.spa import get_spa_pubkey_b64, uid_to_ip
        spa_pubkey = get_spa_pubkey_b64()
        assigned_ip = uid_to_ip(vpn_uid, subnet)

        # Generate WireGuard keypair server-side
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat, PublicFormat,
        )
        priv = X25519PrivateKey.generate()
        wg_privkey = base64.b64encode(
            priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        ).decode()
        wg_pubkey = base64.b64encode(
            priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode()

        # Remove any existing lease + peer before re-provisioning
        leases_col = get_collection("vpn_leases")
        existing_lease = leases_col.find_one({"uid": username})
        if existing_lease and existing_lease.get("pubkey"):
            try:
                sidecar.remove_peer(existing_lease["pubkey"])
            except Exception:
                pass
        leases_col.delete_one({"uid": username})

        # Register peer on sidecar
        try:
            sidecar.add_peer(wg_pubkey, assigned_ip, username)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=f"Sidecar error registering peer: {exc}")

        # Create active lease
        user_doc = get_collection("users").find_one({"username": username}) or {}
        lease_secs = provider.get_effective_lease_seconds(user_doc)
        now = datetime.now(timezone.utc)
        expires_at_iso = _make_expires_at(lease_secs)
        leases_col.insert_one({
            "uid": username,
            "pubkey": wg_pubkey,
            "assigned_ip": assigned_ip,
            "peer_name": username,
            "state": "active",
            "server_pubkey": server_pubkey,
            "expires_at": expires_at_iso,
            "created_at": now.isoformat(),
            "vault_path": f"vpn/{username}",
        })

        # Build full wg.conf and save as vault secret
        routes = provider.get_routes()
        dns_servers = provider.get_dns()
        dns_line = f"DNS = {', '.join(dns_servers)}\n" if dns_servers else ""
        wg_conf = (
            f"[Interface]\n"
            f"PrivateKey = {wg_privkey}\n"
            f"Address = {assigned_ip}/32\n"
            f"{dns_line}"
            f"\n"
            f"[Peer]\n"
            f"PublicKey = {server_pubkey}\n"
            f"Endpoint = {server_endpoint}\n"
            f"AllowedIPs = {', '.join(routes)}\n"
            f"PersistentKeepalive = 25\n"
        )
        _save_vault_secret(
            f"vpn/{username}",
            wg_conf,
            admin,
            description=f"WireGuard peer config for {username}",
            owner=username,
        )

        token_payload = {
            "uid": username,
            "vpn_uid": vpn_uid,
            "seed_b32": seed,
            "knock_host": knock_host,
            "knock_port": knock_port,
            "subnet": subnet,
            "server_vpn_uid": server_vpn_uid,
            "server_endpoint": server_endpoint,
            "server_pubkey": server_pubkey,
            "server_port": settings.VPN_SERVER_PORT,
            "spa_pubkey": spa_pubkey,
            "wg_privkey": wg_privkey,
            "wg_pubkey": wg_pubkey,
            "assigned_ip": assigned_ip,
            "routes": routes,
        }
        provision_token = base64.urlsafe_b64encode(
            json.dumps(token_payload).encode()
        ).decode()

        response = JSONResponse(status_code=201, content={
            "vpn_uid": vpn_uid,
            "provisioning_url": provisioning_url,
            "provision_token": provision_token,
        })
        LogEntry.from_request(
            request=request, response=response,
            resource="secret", resource_id=f"vpn/{username}",
            action="create", success=True,
            extra={
                "context": "vpn_admin_provision_full",
                "provisioned_for": username,
                "assigned_ip": assigned_ip,
                "vpn_uid": vpn_uid,
            },
        ).save_default()
        LogEntry.from_request(
            request=request, response=response,
            resource="vpn_lease", resource_id=username,
            action="grant", success=True,
            extra={
                "assigned_ip": assigned_ip,
                "vpn_uid": vpn_uid,
                "lease_seconds": lease_secs,
                "expires_at": expires_at_iso,
                "provisioned_by": admin,
            },
        ).save_default()
        return response

    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/admin/users/{username}/otp", tags=["vpn"])
def admin_revoke_otp(username: str, admin: str = Depends(_require_admin)):
    """Admin: revoke OTP seed, vpn_uid, active lease, and sidecar peer for username."""
    # Remove sidecar peer + lease if one exists
    lease = get_collection("vpn_leases").find_one({"uid": username})
    if lease:
        try:
            client = _get_provider().get_client()
            if client:
                client.remove_peer(lease["pubkey"])
        except Exception:
            pass
        get_collection("vpn_leases").delete_one({"uid": username})

    # Wipe OTP seed + vpn_uid from user doc
    get_collection("users").update_one(
        {"username": username},
        {"$unset": {"otp_seed_enc": "", "vpn_uid": "", "vpn_uid_assigned_at": ""}},
    )
    return JSONResponse(content={"detail": f"OTP and VPN access revoked for '{username}'"})


class VPNUserSettings(BaseModel):
    vpn_lease_minutes: Optional[int] = None  # None=global, 0=infinite, N=minutes
    vpn_blackout_start: Optional[str] = None  # "HH:MM" UTC, None=disabled
    vpn_blackout_end: Optional[str] = None    # "HH:MM" UTC, None=disabled


@router.patch("/admin/users/{username}/settings", tags=["vpn"])
def admin_update_vpn_settings(
    username: str,
    body: VPNUserSettings,
    admin: str = Depends(_require_admin),
):
    """
    Admin: configure per-user VPN lease duration and/or blackout window.

    vpn_lease_minutes:
      null  → use global lease_hours from integration config
      0     → infinite (never expires)
      N     → N minutes

    vpn_blackout_start / vpn_blackout_end:
      Both must be set together (HH:MM, UTC). Set both to null to disable.
      Cross-midnight ranges supported (e.g. start=20:00, end=08:00).
    """
    import re

    users_col = get_collection("users")
    user = users_col.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")

    if body.vpn_lease_minutes is not None and body.vpn_lease_minutes < 0:
        raise HTTPException(status_code=422, detail="vpn_lease_minutes must be 0 (infinite) or positive")

    hhmm = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
    blackout_start = body.vpn_blackout_start
    blackout_end = body.vpn_blackout_end

    if (blackout_start is None) != (blackout_end is None):
        raise HTTPException(status_code=422, detail="Both vpn_blackout_start and vpn_blackout_end must be set together")
    if blackout_start and not hhmm.match(blackout_start):
        raise HTTPException(status_code=422, detail=f"Invalid vpn_blackout_start: '{blackout_start}' (use HH:MM)")
    if blackout_end and not hhmm.match(blackout_end):
        raise HTTPException(status_code=422, detail=f"Invalid vpn_blackout_end: '{blackout_end}' (use HH:MM)")

    update: dict = {}
    unset: dict = {}

    if body.vpn_lease_minutes is None:
        unset["vpn_lease_minutes"] = ""
    else:
        update["vpn_lease_minutes"] = body.vpn_lease_minutes

    if blackout_start is None:
        unset["vpn_blackout_start"] = ""
        unset["vpn_blackout_end"] = ""
    else:
        update["vpn_blackout_start"] = blackout_start
        update["vpn_blackout_end"] = blackout_end

    mongo_op: dict = {}
    if update:
        mongo_op["$set"] = update
    if unset:
        mongo_op["$unset"] = unset

    if mongo_op:
        users_col.update_one({"username": username}, mongo_op)

    # Sync expires_at on the active lease so the new policy takes effect immediately
    leases_col = get_collection("vpn_leases")
    active_lease = leases_col.find_one({"uid": username, "state": "active"})
    if active_lease:
        updated_user = dict(user)
        if body.vpn_lease_minutes is None:
            updated_user.pop("vpn_lease_minutes", None)
        else:
            updated_user["vpn_lease_minutes"] = body.vpn_lease_minutes
        provider = _get_provider()
        lease_secs = provider.get_effective_lease_seconds(updated_user)
        now = datetime.now(timezone.utc)
        new_expires_at = None if lease_secs is None else (now + timedelta(seconds=lease_secs)).isoformat()
        leases_col.update_one(
            {"_id": active_lease["_id"]},
            {"$set": {"expires_at": new_expires_at}},
        )

    return JSONResponse(content={
        "detail": f"VPN settings updated for '{username}'",
        "vpn_lease_minutes": body.vpn_lease_minutes,
        "vpn_blackout_start": blackout_start,
        "vpn_blackout_end": blackout_end,
    })


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
    user_doc = get_collection("users").find_one({"username": current_user}) or {}
    lease_secs = provider.get_effective_lease_seconds(user_doc)
    now = datetime.now(timezone.utc)
    expires_at_iso = _make_expires_at(lease_secs)

    leases_col.update_one(
        {"uid": current_user},
        {"$set": {
            "state": "active",
            "expires_at": expires_at_iso,
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

    routes = provider.get_routes()
    return JSONResponse(content={
        "assigned_ip": lease["assigned_ip"],
        "server_pubkey": server_pubkey,
        "server_endpoint": server_endpoint,
        "lease_expires": expires_at_iso,
        "routes": routes,
        "wg_conf": wg_conf,
    })
