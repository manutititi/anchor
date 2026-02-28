"""
Atomic IP allocation pool backed by MongoDB.

Collection: vpn_ip_pool
Schema: { "_id": "10.13.13.X", "status": "free"|"leased", "uid": str|None }

The .0 (network) and .255 (broadcast) addresses are automatically excluded
by ipaddress.hosts(). The .1 address (server VPN IP) is also skipped.
"""
import ipaddress
from typing import Optional

from db.client import get_collection

COLLECTION = "vpn_ip_pool"


def init_pool(subnet: str) -> int:
    """
    Populate vpn_ip_pool from a CIDR subnet.
    Only inserts IPs that are not already present (idempotent).
    Returns the number of new IPs inserted.
    """
    net = ipaddress.IPv4Network(subnet, strict=False)
    col = get_collection(COLLECTION)

    # Reserve .1 for the server's VPN interface
    server_ip = str(net.network_address + 1)

    inserted = 0
    for host in net.hosts():  # ipaddress.hosts() excludes network + broadcast
        ip = str(host)
        if ip == server_ip:
            continue
        if not col.find_one({"_id": ip}):
            col.insert_one({"_id": ip, "status": "free", "uid": None})
            inserted += 1

    return inserted


def allocate_ip(uid: str) -> Optional[str]:
    """
    Atomically allocate a free IP to uid.
    Uses findOneAndUpdate for race-condition safety.
    Returns the assigned IP string, or None if the pool is exhausted.
    """
    col = get_collection(COLLECTION)
    doc = col.find_one_and_update(
        {"status": "free"},
        {"$set": {"status": "leased", "uid": uid}},
        return_document=True,
    )
    return doc["_id"] if doc else None


def free_ip(ip: str) -> None:
    """Release a leased IP back to the free pool."""
    get_collection(COLLECTION).update_one(
        {"_id": ip},
        {"$set": {"status": "free", "uid": None}},
    )


def pool_status() -> dict:
    """Return a summary of free/leased/total counts."""
    col = get_collection(COLLECTION)
    total = col.count_documents({})
    leased = col.count_documents({"status": "leased"})
    return {"total": total, "leased": leased, "free": total - leased}
