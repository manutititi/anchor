"""
UDP Knock Listener — SPA V2 (Single Packet Authorization with ECDH).

Binds to a UDP port and silently processes each incoming packet:
  1. parse_packet() — ECDH + AES-GCM decryption (ephemeral pubkey → shared secret)
  2. Nonce anti-replay via vpn_nonces TTL collection (unique index on nonce)
  3. vpn_uid lookup → username from users collection
  4. OTP verification via vpn/otp.verify_otp()
  5. Deterministic IP from vpn_uid + subnet
  6. sidecar.add_peer() — registers peer with AllowedIPs = assigned_ip/32
  7. vpn_leases insert with state="onboarding", expires_at=now+5min

Any failure at any step is a silent drop (no response to sender).
The onboarding lease is promoted to "active" later via POST /vpn/promote.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from db.client import get_collection
from vpn.otp import verify_otp
from vpn.spa import EPH_PUBKEY_SIZE, NONCE_SIZE, parse_packet, uid_to_ip

logger = logging.getLogger(__name__)


class KnockProtocol(asyncio.DatagramProtocol):
    """asyncio UDP protocol that handles SPA V2 knock packets."""

    def __init__(self, subnet: str, spa_privkey: X25519PrivateKey) -> None:
        self.subnet = subnet
        self.spa_privkey = spa_privkey
        self._transport = None

    def connection_made(self, transport) -> None:
        self._transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        asyncio.ensure_future(self._handle(data, addr))

    async def _handle(self, data: bytes, addr) -> None:
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._process, data, addr)
        except Exception as exc:
            logger.debug("Knock: unexpected error from %s: %s", addr, exc)

    def _process(self, data: bytes, addr) -> None:
        """Synchronous packet processing — runs in a thread pool executor."""

        # Step 1: ECDH + AES-GCM decrypt → SPAData(vpn_uid, otp, ts, wg_pubkey)
        spa = parse_packet(data, self.spa_privkey)
        if spa is None:
            return  # silent drop

        # Step 2: anti-replay — insert nonce; duplicate = replay → drop
        # Nonce is at offset EPH_PUBKEY_SIZE (after the ephemeral pubkey)
        nonce_hex = data[EPH_PUBKEY_SIZE : EPH_PUBKEY_SIZE + NONCE_SIZE].hex()
        try:
            get_collection("vpn_nonces").insert_one({
                "nonce": nonce_hex,
                "created_at": datetime.now(timezone.utc),
            })
        except Exception:
            # Unique index violation = nonce already seen → replay attack
            return

        # Step 3: lookup username by vpn_uid
        user_doc = get_collection("users").find_one(
            {"vpn_uid": spa.vpn_uid}, {"username": 1, "vpn_uid": 1}
        )
        if not user_doc or "username" not in user_doc:
            logger.warning("Knock: no user found for vpn_uid=%d from %s", spa.vpn_uid, addr)
            return

        username = user_doc["username"]

        # Step 4: OTP verification
        if not verify_otp(username, spa.otp):
            logger.warning("Knock: OTP failed for vpn_uid=%d from %s", spa.vpn_uid, addr)
            return

        # Step 5: deterministic IP from vpn_uid
        assigned_ip = uid_to_ip(spa.vpn_uid, self.subnet)

        # Step 6: handle existing lease — allow re-knock (revoke + re-register)
        leases_col = get_collection("vpn_leases")
        existing = leases_col.find_one({"uid": username})
        if existing:
            # Always clean up the old peer so the new knock can register fresh.
            # This allows re-knocking even over an active lease (e.g. after
            # reconnection, IP change, or device swap).
            logger.info(
                "Knock: cleaning up existing lease (state=%s) for uid=%s",
                existing.get("state", "?"), username,
            )
            try:
                from integrations.wireguard.provider import WireGuardProvider
                _client = WireGuardProvider().get_client()
                if _client and existing.get("pubkey"):
                    _client.remove_peer(existing["pubkey"])
            except Exception as exc:
                logger.warning("Knock: could not remove old peer for uid=%s: %s", username, exc)
            leases_col.delete_one({"uid": username})

        # Step 7: register peer on WireGuard sidecar (AllowedIPs = ip/32)
        try:
            from integrations.wireguard.provider import WireGuardProvider
            client = WireGuardProvider().get_client()
            if client:
                client.add_peer(spa.wg_pubkey, assigned_ip, username)
        except Exception as exc:
            logger.error("Knock: sidecar error for uid=%s: %s", username, exc)
            return

        # Step 8: create onboarding lease (expires in 5 min if not promoted)
        now = datetime.now(timezone.utc)
        leases_col.insert_one({
            "uid": username,
            "vpn_uid": spa.vpn_uid,
            "pubkey": spa.wg_pubkey,
            "assigned_ip": assigned_ip,
            "peer_name": username,
            "state": "onboarding",
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
            "created_at": now.isoformat(),
        })

        logger.info(
            "Knock: peer registered uid=%s vpn_uid=%d ip=%s src=%s",
            username, spa.vpn_uid, assigned_ip, addr,
        )


async def start_knock_listener(
    host: str,
    port: int,
    subnet: str,
    spa_privkey: X25519PrivateKey,
) -> None:
    """
    Start the SPA V2 UDP knock listener.
    Called from server.py lifespan via asyncio.ensure_future().
    """
    loop = asyncio.get_event_loop()
    logger.info("SPA V2 knock listener starting on udp %s:%d", host, port)

    transport, _ = await loop.create_datagram_endpoint(
        lambda: KnockProtocol(subnet, spa_privkey),
        local_addr=(host, port),
    )
    logger.info("SPA V2 knock listener active on udp %s:%d", host, port)

    try:
        await asyncio.Future()  # run forever
    finally:
        transport.close()
        logger.info("SPA V2 knock listener stopped")
