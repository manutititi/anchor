"""
Async background janitor: cleans up expired VPN leases and manages
blackout windows (temporary peer suspension).

Started as an asyncio task in server.py lifespan. Errors are swallowed so the
loop never crashes — individual failures are logged.

Blackout window logic
---------------------
Each user can have vpn_blackout_start and vpn_blackout_end stored on their
user document (HH:MM strings, interpreted as UTC).  When the janitor runs:
  - If we are inside the blackout window and the peer is active
    (lease.blackout_active is falsy) → remove peer from sidecar, set
    lease.blackout_active = True.
  - If we are outside the blackout window and the peer was suspended
    (lease.blackout_active is True) → re-add peer to sidecar, clear flag.

Cross-midnight windows are supported (e.g. 20:00 → 08:00).
"""
import asyncio
import logging
from datetime import datetime, timezone

from db.client import get_collection
from vpn.ip_pool import free_ip

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _in_blackout(start: str, end: str, now: datetime) -> bool:
    """
    Return True if *now* (UTC) falls inside the [start, end) window.
    start and end are "HH:MM" strings (UTC).  Cross-midnight is supported.
    """
    try:
        sh, sm = int(start[:2]), int(start[3:])
        eh, em = int(end[:2]), int(end[3:])
    except (ValueError, IndexError):
        return False

    current_minutes = now.hour * 60 + now.minute
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em

    if start_minutes <= end_minutes:
        # Same-day window, e.g. 09:00 → 17:00
        return start_minutes <= current_minutes < end_minutes
    else:
        # Cross-midnight window, e.g. 20:00 → 08:00
        return current_minutes >= start_minutes or current_minutes < end_minutes


def _get_sidecar_client():
    try:
        from integrations.wireguard.provider import WireGuardProvider
        return WireGuardProvider().get_client()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cleanup: remove expired leases
# ---------------------------------------------------------------------------

def _cleanup_expired(now: datetime) -> int:
    """
    Remove leases whose expires_at < now (ignoring leases with no expires_at,
    which are infinite).  Calls sidecar.remove_peer() for each, then frees
    the IP slot.  Returns the number of leases removed.
    """
    now_iso = now.isoformat()
    leases_col = get_collection("vpn_leases")

    # Only match docs where expires_at field exists, is not null, and is past
    expired = list(leases_col.find({
        "expires_at": {"$type": "string", "$lt": now_iso},
    }))
    if not expired:
        return 0

    client = _get_sidecar_client()
    removed = 0
    for lease in expired:
        if client:
            try:
                client.remove_peer(lease["pubkey"])
            except Exception as exc:
                logger.warning(
                    "Janitor: failed to remove peer %s from sidecar: %s",
                    lease.get("pubkey", "?")[:8],
                    exc,
                )

        try:
            free_ip(lease["assigned_ip"])
        except Exception as exc:
            logger.warning("Janitor: free_ip failed for %s: %s", lease.get("assigned_ip"), exc)

        leases_col.delete_one({"_id": lease["_id"]})
        removed += 1
        logger.info(
            "Janitor: expired lease removed — uid=%s ip=%s expires_at=%s",
            lease.get("uid"),
            lease.get("assigned_ip"),
            lease.get("expires_at"),
        )

    return removed


# ---------------------------------------------------------------------------
# Blackout window: suspend / resume peers
# ---------------------------------------------------------------------------

def _manage_blackouts(now: datetime) -> None:
    """
    For every active lease whose user has a blackout window configured:
      - Entering blackout → remove peer from sidecar, mark blackout_active=True
      - Leaving  blackout → re-add peer to sidecar,  clear blackout_active
    """
    leases_col = get_collection("vpn_leases")
    users_col = get_collection("users")

    # Only look at active leases (not onboarding, not already-expired)
    leases = list(leases_col.find({"state": "active"}, {"_id": 1, "uid": 1, "pubkey": 1,
                                                          "assigned_ip": 1, "peer_name": 1,
                                                          "blackout_active": 1}))
    if not leases:
        return

    # Fetch user docs for all relevant uids in one query
    uids = [l["uid"] for l in leases]
    user_map = {
        u["username"]: u
        for u in users_col.find(
            {"username": {"$in": uids},
             "vpn_blackout_start": {"$exists": True},
             "vpn_blackout_end":   {"$exists": True}},
            {"username": 1, "vpn_blackout_start": 1, "vpn_blackout_end": 1},
        )
    }

    if not user_map:
        return

    client = _get_sidecar_client()

    for lease in leases:
        uid = lease["uid"]
        user = user_map.get(uid)
        if not user:
            continue  # no blackout configured for this user

        b_start = user.get("vpn_blackout_start")
        b_end = user.get("vpn_blackout_end")
        if not b_start or not b_end:
            continue

        in_blackout = _in_blackout(b_start, b_end, now)
        is_suspended = bool(lease.get("blackout_active"))

        if in_blackout and not is_suspended:
            # Suspend the peer
            if client:
                try:
                    client.remove_peer(lease["pubkey"])
                    leases_col.update_one(
                        {"_id": lease["_id"]},
                        {"$set": {"blackout_active": True}},
                    )
                    logger.info(
                        "Janitor: blackout started for uid=%s (%s → %s)",
                        uid, b_start, b_end,
                    )
                except Exception as exc:
                    logger.warning(
                        "Janitor: failed to suspend peer for uid=%s: %s", uid, exc
                    )

        elif not in_blackout and is_suspended:
            # Resume the peer
            if client:
                try:
                    client.add_peer(
                        lease["pubkey"],
                        lease["assigned_ip"],
                        lease.get("peer_name", uid),
                    )
                    leases_col.update_one(
                        {"_id": lease["_id"]},
                        {"$unset": {"blackout_active": ""}},
                    )
                    logger.info("Janitor: blackout ended, peer resumed for uid=%s", uid)
                except Exception as exc:
                    logger.warning(
                        "Janitor: failed to resume peer for uid=%s: %s", uid, exc
                    )


# ---------------------------------------------------------------------------
# Main sync entry point (called from the async loop via run_in_executor)
# ---------------------------------------------------------------------------

def _run_cycle() -> None:
    now = _now_utc()
    removed = _cleanup_expired(now)
    if removed:
        logger.info("Janitor: removed %d expired lease(s)", removed)
    _manage_blackouts(now)


# ---------------------------------------------------------------------------
# Async loop
# ---------------------------------------------------------------------------

async def start_janitor(interval_sec: int = 300) -> None:
    """
    Run the cleanup loop indefinitely.
    Designed to be started with asyncio.create_task() in the server lifespan.
    """
    logger.info("VPN janitor started (interval=%ds)", interval_sec)
    while True:
        await asyncio.sleep(interval_sec)
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _run_cycle)
        except Exception as exc:
            logger.exception("Janitor: unexpected error: %s", exc)
