"""
SPA (Single Packet Authorization) packet builder / parser.

Packet layout — 154 bytes total:
  [  64 B  uid_raw    ]  username, null-padded (plaintext, for seed lookup)
  [  16 B  nonce      ]  random AES-GCM nonce
  [  58 B  ciphertext ]  AES-256-GCM encrypted payload (same length as plaintext)
  [  16 B  auth tag   ]  GCM authentication tag

AES payload (plaintext, 58 bytes):
  [  6 B  otp      ]  TOTP code — ASCII digits, null-padded
  [  8 B  timestamp]  Unix epoch — uint64 big-endian
  [ 44 B  wg_pubkey]  WireGuard public key — base64 ASCII, null-padded

AES key derivation:
  HKDF-SHA256(master=base32decode(seed_b32), key_len=32,
              salt=b"spa-v1", context=uid_str.encode())

Anti-replay: the 16-byte nonce must be unique in the vpn_nonces TTL collection
(TTL 60 s).  Timestamp is also checked for ±2 s skew.
"""
import base64
import ipaddress
import struct
import time
from dataclasses import dataclass
from typing import Callable, Optional

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.Random import get_random_bytes

# ---------------------------------------------------------------------------
# Packet constants
# ---------------------------------------------------------------------------

UID_SIZE = 64        # bytes reserved for username in the packet
NONCE_SIZE = 16      # AES-GCM nonce
OTP_SIZE = 6         # TOTP code (ASCII digits)
TS_SIZE = 8          # uint64 big-endian timestamp
PUBKEY_SIZE = 44     # WireGuard base64 public key
TAG_SIZE = 16        # GCM authentication tag

PLAINTEXT_SIZE = OTP_SIZE + TS_SIZE + PUBKEY_SIZE    # 58
PACKET_SIZE = UID_SIZE + NONCE_SIZE + PLAINTEXT_SIZE + TAG_SIZE  # 154

# Maximum allowed clock skew in seconds
TIMESTAMP_WINDOW = 2


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class SPAData:
    uid: str        # username (resolved from uid_raw)
    otp: str        # 6-digit TOTP code
    timestamp: int  # Unix epoch from packet
    wg_pubkey: str  # WireGuard public key (base64)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_key(seed_b32: str, uid: str) -> bytes:
    seed_bytes = base64.b32decode(seed_b32)
    return HKDF(
        master=seed_bytes,
        key_len=32,
        salt=b"spa-v1",
        hashmod=SHA256,
        context=uid.encode(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def uid_to_ip(uid: int, subnet: str) -> str:
    """
    Deterministically compute the VPN IP for a given integer UID.
    UID=1 → subnet.1 (WireGuard server), UID=2 → subnet.2, etc.
    No database required — pure arithmetic.
    """
    net = ipaddress.IPv4Network(subnet, strict=False)
    return str(net.network_address + uid)


def build_packet(uid_str: str, otp_str: str, wg_pubkey: str, seed_b32: str) -> bytes:
    """
    Build a 154-byte SPA UDP packet ready to send to the knock listener.

    Args:
        uid_str:   Username (padded/truncated to UID_SIZE in the packet).
        otp_str:   Current TOTP code (6 ASCII digits).
        wg_pubkey: WireGuard public key (44-char base64 string).
        seed_b32:  TOTP seed (base32), used to derive the AES key.
    """
    ts = int(time.time())
    uid_raw = uid_str.encode().ljust(UID_SIZE, b"\x00")[:UID_SIZE]
    nonce = get_random_bytes(NONCE_SIZE)
    key = _derive_key(seed_b32, uid_str)

    plaintext = (
        otp_str.encode().ljust(OTP_SIZE, b"\x00")[:OTP_SIZE]
        + struct.pack(">Q", ts)
        + wg_pubkey.encode().ljust(PUBKEY_SIZE, b"\x00")[:PUBKEY_SIZE]
    )

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return uid_raw + nonce + ciphertext + tag


def parse_packet(
    data: bytes,
    seed_fn: Callable[[str], Optional[str]],
) -> Optional[SPAData]:
    """
    Parse and cryptographically validate an SPA packet.

    Returns SPAData on success, None on any failure (silent drop semantics).
    Validates: exact packet size, seed existence, AES-GCM auth tag, timestamp skew.
    Anti-replay (nonce uniqueness) must be enforced by the caller (knock.py).

    Args:
        data:     Raw UDP payload.
        seed_fn:  Callable[username → seed_b32 | None] — the caller provides
                  a DB lookup function so this module stays pure/testable.
    """
    if len(data) != PACKET_SIZE:
        return None

    uid_raw = data[:UID_SIZE]
    nonce = data[UID_SIZE : UID_SIZE + NONCE_SIZE]
    ciphertext = data[UID_SIZE + NONCE_SIZE : UID_SIZE + NONCE_SIZE + PLAINTEXT_SIZE]
    tag = data[UID_SIZE + NONCE_SIZE + PLAINTEXT_SIZE :]

    uid_str = uid_raw.rstrip(b"\x00").decode(errors="replace")
    seed = seed_fn(uid_str)
    if not seed:
        return None

    key = _derive_key(seed, uid_str)
    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    except Exception:
        return None

    otp_str = plaintext[:OTP_SIZE].rstrip(b"\x00").decode(errors="replace")
    ts = struct.unpack(">Q", plaintext[OTP_SIZE : OTP_SIZE + TS_SIZE])[0]
    wg_pubkey = (
        plaintext[OTP_SIZE + TS_SIZE :]
        .rstrip(b"\x00")
        .decode(errors="replace")
    )

    if abs(int(time.time()) - ts) > TIMESTAMP_WINDOW:
        return None

    return SPAData(uid=uid_str, otp=otp_str, timestamp=ts, wg_pubkey=wg_pubkey)
