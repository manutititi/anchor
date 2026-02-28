"""
Async background janitor: cleans up expired VPN leases every N seconds.

Started as an asyncio task in server.py lifespan. Errors are swallowed so the
loop never crashes — individual failures are logged.
"""
import asyncio
import logging
from datetime import datetime, timezone

from db.client import get_collection
from vpn.ip_pool import free_ip

logger = logging.getLogger(__name__)


def _cleanup_expired() -> int:
    """
    Synchronous cleanup: remove leases whose expires_at < now.
    Calls sidecar.remove_peer() for each, then frees the IP.
    Returns the number of leases removed.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    leases_col = get_collection("vpn_leases")
    expired = list(leases_col.find({"expires_at": {"$lt": now_iso}}))
    if not expired:
        return 0

    try:
        from integrations.wireguard.provider import WireGuardProvider
        client = WireGuardProvider().get_client()
    except Exception:
        client = None

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

        free_ip(lease["assigned_ip"])
        leases_col.delete_one({"_id": lease["_id"]})
        removed += 1
        logger.info(
            "Janitor: expired lease removed — uid=%s ip=%s",
            lease.get("uid"),
            lease.get("assigned_ip"),
        )

    return removed


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
            removed = await loop.run_in_executor(None, _cleanup_expired)
            if removed:
                logger.info("Janitor: removed %d expired lease(s)", removed)
        except Exception as exc:
            logger.exception("Janitor: unexpected error: %s", exc)
