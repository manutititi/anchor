"""
SPA V2 (Single Packet Authorization) — ECDH-based packet builder / parser.

Packet layout — 126 bytes total:
  [  32 B  eph_pubkey ]  X25519 ephemeral public key (for ECDH)
  [  16 B  nonce      ]  AES-GCM nonce
  [  62 B  ciphertext ]  AES-256-GCM encrypted payload
  [  16 B  auth tag   ]  GCM authentication tag

Encrypted payload (plaintext, 62 bytes):
  [  4 B  vpn_uid   ]  uint32 big-endian — numeric user identifier
  [  6 B  otp       ]  TOTP code — ASCII digits, null-padded
  [  8 B  timestamp ]  Unix epoch — uint64 big-endian
  [ 44 B  wg_pubkey ]  WireGuard public key — base64 ASCII, null-padded

Key derivation:
  shared_secret = X25519(server_privkey, eph_pubkey)     — or —
  shared_secret = X25519(eph_privkey, server_pubkey)
  aes_key = HKDF-SHA256(shared_secret, salt=b"spa-v2", key_len=32)

Zero secrets on the client: the client only knows the server's SPA public
key (non-confidential).  The TOTP seed never leaves the server.
Ephemeral keypair per knock → forward secrecy.

Anti-replay: the 16-byte nonce must be unique in the vpn_nonces TTL collection
(TTL 60 s).  Timestamp is also checked for ±30 s skew.
"""
import base64
import ipaddress
import struct
import time
from dataclasses import dataclass
from typing import Optional

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.Random import get_random_bytes

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)

# ---------------------------------------------------------------------------
# Packet constants
# ---------------------------------------------------------------------------

EPH_PUBKEY_SIZE = 32   # X25519 public key (raw bytes)
NONCE_SIZE = 16        # AES-GCM nonce
VPN_UID_SIZE = 4       # uint32 big-endian
OTP_SIZE = 6           # TOTP code (ASCII digits)
TS_SIZE = 8            # uint64 big-endian timestamp
PUBKEY_SIZE = 44       # WireGuard base64 public key
TAG_SIZE = 16          # GCM authentication tag

PLAINTEXT_SIZE = VPN_UID_SIZE + OTP_SIZE + TS_SIZE + PUBKEY_SIZE   # 62
PACKET_SIZE = EPH_PUBKEY_SIZE + NONCE_SIZE + PLAINTEXT_SIZE + TAG_SIZE  # 126

# Maximum allowed clock skew in seconds.
TIMESTAMP_WINDOW = 30


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class SPAData:
    vpn_uid: int    # numeric VPN user identifier
    otp: str        # 6-digit TOTP code
    timestamp: int  # Unix epoch from packet
    wg_pubkey: str  # WireGuard public key (base64)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def load_privkey(b64: str) -> X25519PrivateKey:
    """Load an X25519 private key from base64."""
    return X25519PrivateKey.from_private_bytes(base64.b64decode(b64))


def load_pubkey(b64: str) -> X25519PublicKey:
    """Load an X25519 public key from base64."""
    return X25519PublicKey.from_public_bytes(base64.b64decode(b64))


def derive_pubkey(privkey: X25519PrivateKey) -> str:
    """Derive the base64-encoded public key from a private key."""
    return base64.b64encode(privkey.public_key().public_bytes_raw()).decode()


def _ecdh_derive_key(shared_secret: bytes) -> bytes:
    """Derive a 32-byte AES key from an ECDH shared secret via HKDF."""
    return HKDF(
        master=shared_secret,
        key_len=32,
        salt=b"spa-v2",
        hashmod=SHA256,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def uid_to_ip(uid: int, subnet: str) -> str:
    """
    Deterministically compute the VPN IP for a given integer UID.
    UID=1 → subnet.1 (WireGuard server), UID=2 → subnet.2, etc.
    """
    net = ipaddress.IPv4Network(subnet, strict=False)
    return str(net.network_address + uid)


def build_packet(
    vpn_uid: int,
    otp_str: str,
    wg_pubkey: str,
    server_pubkey: X25519PublicKey,
) -> bytes:
    """
    Build a 126-byte SPA V2 UDP packet.

    Uses an ephemeral X25519 keypair for ECDH key agreement with the
    server's SPA public key.  The vpn_uid, TOTP code, timestamp and
    WireGuard public key are all encrypted — zero plaintext metadata.

    Args:
        vpn_uid:       Numeric VPN user ID (uint32).
        otp_str:       Current TOTP code (6 ASCII digits).
        wg_pubkey:     WireGuard public key (44-char base64 string).
        server_pubkey: Server's SPA X25519 public key object.
    """
    # Ephemeral ECDH keypair (forward secrecy)
    eph_priv = X25519PrivateKey.generate()
    eph_pub_bytes = eph_priv.public_key().public_bytes_raw()  # 32 bytes

    # Shared secret → AES key
    shared = eph_priv.exchange(server_pubkey)
    key = _ecdh_derive_key(shared)

    # Build plaintext
    ts = int(time.time())
    plaintext = (
        struct.pack(">I", vpn_uid)
        + otp_str.encode().ljust(OTP_SIZE, b"\x00")[:OTP_SIZE]
        + struct.pack(">Q", ts)
        + wg_pubkey.encode().ljust(PUBKEY_SIZE, b"\x00")[:PUBKEY_SIZE]
    )

    # AES-256-GCM encrypt
    nonce = get_random_bytes(NONCE_SIZE)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)

    return eph_pub_bytes + nonce + ciphertext + tag


def parse_packet(
    data: bytes,
    server_privkey: X25519PrivateKey,
) -> Optional[SPAData]:
    """
    Parse and cryptographically validate an SPA V2 packet.

    Returns SPAData on success, None on any failure (silent drop).
    Validates: exact packet size, ECDH + AES-GCM auth tag, timestamp skew.
    Anti-replay (nonce uniqueness) must be enforced by the caller (knock.py).

    Args:
        data:           Raw UDP payload (126 bytes expected).
        server_privkey: Server's SPA X25519 private key for ECDH.
    """
    if len(data) != PACKET_SIZE:
        return None

    # Split packet
    eph_pub_bytes = data[:EPH_PUBKEY_SIZE]
    nonce = data[EPH_PUBKEY_SIZE : EPH_PUBKEY_SIZE + NONCE_SIZE]
    ct_start = EPH_PUBKEY_SIZE + NONCE_SIZE
    ciphertext = data[ct_start : ct_start + PLAINTEXT_SIZE]
    tag = data[ct_start + PLAINTEXT_SIZE :]

    # ECDH → shared secret → AES key
    try:
        eph_pubkey = X25519PublicKey.from_public_bytes(eph_pub_bytes)
        shared = server_privkey.exchange(eph_pubkey)
    except Exception:
        return None

    key = _ecdh_derive_key(shared)

    # Decrypt
    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    except Exception:
        return None

    # Unpack fields
    vpn_uid = struct.unpack(">I", plaintext[:VPN_UID_SIZE])[0]
    otp_str = (
        plaintext[VPN_UID_SIZE : VPN_UID_SIZE + OTP_SIZE]
        .rstrip(b"\x00")
        .decode(errors="replace")
    )
    ts = struct.unpack(
        ">Q",
        plaintext[VPN_UID_SIZE + OTP_SIZE : VPN_UID_SIZE + OTP_SIZE + TS_SIZE],
    )[0]
    wg_pubkey = (
        plaintext[VPN_UID_SIZE + OTP_SIZE + TS_SIZE :]
        .rstrip(b"\x00")
        .decode(errors="replace")
    )

    # Timestamp check
    if abs(int(time.time()) - ts) > TIMESTAMP_WINDOW:
        return None

    return SPAData(vpn_uid=vpn_uid, otp=otp_str, timestamp=ts, wg_pubkey=wg_pubkey)
