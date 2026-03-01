"""
UDP Knock Listener — SPA (Single Packet Authorization).

Binds to a UDP port and silently processes each incoming packet:
  1. parse_packet() — cryptographic validation (uid, OTP, timestamp, AES-GCM)
  2. Nonce anti-replay via vpn_nonces TTL collection (unique index on nonce)
  3. OTP verification via vpn/otp.verify_otp()
  4. vpn_uid lookup from users collection → deterministic IP assignment
  5. sidecar.add_peer() — registers peer with AllowedIPs = assigned_ip/32
  6. vpn_leases insert with state="onboarding", expires_at=now+5min

Any failure at any step is a silent drop (no response to sender).
The onboarding lease is promoted to "active" later via POST /vpn/promote.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from db.client import get_collection
from vpn.otp import get_otp_seed, verify_otp
from vpn.spa import parse_packet, uid_to_ip

logger = logging.getLogger(__name__)


class KnockProtocol(asyncio.DatagramProtocol):
    """asyncio UDP protocol that handles SPA knock packets."""

    def __init__(self, subnet: str) -> None:
        self.subnet = subnet
        self._transport = None

    def connection_made(self, transport) -> None:
        self._transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        # Schedule processing in a thread executor to keep the event loop free
        asyncio.ensure_future(self._handle(data, addr))

    async def _handle(self, data: bytes, addr) -> None:
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._process, data, addr)
        except Exception as exc:
            logger.debug("Knock: unexpected error from %s: %s", addr, exc)

    def _process(self, data: bytes, addr) -> None:
        """Synchronous packet processing — runs in a thread pool executor."""

        # Step 1: parse + crypto validation
        spa = parse_packet(data, get_otp_seed)
        if spa is None:
            return  # silent drop

        # Step 2: anti-replay — insert nonce; duplicate = replay → drop
        nonce_hex = data[64:80].hex()
        try:
            get_collection("vpn_nonces").insert_one({
                "nonce": nonce_hex,
                "created_at": datetime.now(timezone.utc),
            })
        except Exception:
            # Unique index violation means nonce already seen → replay attack
            return

        # Step 3: OTP verification
        if not verify_otp(spa.uid, spa.otp):
            logger.warning("Knock: OTP failed for uid=%s from %s", spa.uid, addr)
            return

        # Step 4: look up integer vpn_uid for deterministic IP
        user_doc = get_collection("users").find_one(
            {"username": spa.uid}, {"vpn_uid": 1}
        )
        if not user_doc or "vpn_uid" not in user_doc:
            logger.warning("Knock: no vpn_uid assigned for uid=%s", spa.uid)
            return

        assigned_ip = uid_to_ip(user_doc["vpn_uid"], self.subnet)

        # Step 5: idempotency — if a lease already exists, drop (no double-add)
        leases_col = get_collection("vpn_leases")
        if leases_col.find_one({"uid": spa.uid}):
            return

        # Step 6: register peer on WireGuard sidecar (AllowedIPs = ip/32)
        try:
            from integrations.wireguard.provider import WireGuardProvider
            client = WireGuardProvider().get_client()
            if client:
                client.add_peer(spa.wg_pubkey, assigned_ip, spa.uid)
        except Exception as exc:
            logger.error("Knock: sidecar error for uid=%s: %s", spa.uid, exc)
            return

        # Step 7: create onboarding lease (expires in 5 min if not promoted)
        now = datetime.now(timezone.utc)
        leases_col.insert_one({
            "uid": spa.uid,
            "pubkey": spa.wg_pubkey,
            "assigned_ip": assigned_ip,
            "peer_name": spa.uid,
            "state": "onboarding",
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
            "created_at": now.isoformat(),
        })

        logger.info(
            "Knock: peer registered uid=%s ip=%s src=%s",
            spa.uid, assigned_ip, addr,
        )


async def start_knock_listener(host: str, port: int, subnet: str) -> None:
    """
    Start the SPA UDP knock listener.
    Called from server.py lifespan via asyncio.ensure_future().
    Runs until the event loop is cancelled.
    """
    loop = asyncio.get_event_loop()
    logger.info("SPA knock listener starting on udp %s:%d", host, port)

    transport, _ = await loop.create_datagram_endpoint(
        lambda: KnockProtocol(subnet),
        local_addr=(host, port),
    )
    logger.info("SPA knock listener active on udp %s:%d", host, port)

    try:
        await asyncio.Future()  # run forever
    finally:
        transport.close()
        logger.info("SPA knock listener stopped")
