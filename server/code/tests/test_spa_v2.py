"""
SPA v2 crypto roundtrip tests — no MongoDB, no server infrastructure required.

Run from server/code/:
  python -m pytest tests/test_spa_v2.py -v
"""
import os
import struct
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

# Add server/code to path if needed
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from vpn.spa import (
    PACKET_SIZE, VERSION, _OFF_NONCE, _OFF_VER,
    NONCE_SIZE, PAYLOAD_SIZE, EPHEMERAL_PUB_SIZE, TAG_SIZE,
    SPAData, build_packet, parse_packet, uid_to_ip, init_server_keypair,
    get_spa_pubkey_b64,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def server_keypair():
    """Generate a server keypair for all tests in this module."""
    priv = X25519PrivateKey.generate()
    priv_b64 = __import__("base64").b64encode(
        priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    ).decode()
    pub_b64 = __import__("base64").b64encode(
        priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    init_server_keypair(priv_b64)
    return priv, priv_b64, pub_b64


@pytest.fixture
def sample_packet(server_keypair):
    _, _, pub_b64 = server_keypair
    return build_packet(
        uid_str="alice",
        otp_str="123456",
        wg_pubkey="A" * 44,
        server_spa_pubkey_b64=pub_b64,
    )


# ---------------------------------------------------------------------------
# Packet size and structure
# ---------------------------------------------------------------------------

def test_packet_size(sample_packet):
    assert len(sample_packet) == PACKET_SIZE == 186


def test_version_bytes(sample_packet):
    assert sample_packet[_OFF_VER:] == VERSION == b"\x00\x02\x00\x00"


# ---------------------------------------------------------------------------
# Successful roundtrip
# ---------------------------------------------------------------------------

def test_roundtrip_basic(server_keypair, sample_packet):
    priv, _, _ = server_keypair
    result = parse_packet(sample_packet, server_privkey=priv)
    assert result is not None
    assert isinstance(result, SPAData)
    assert result.uid == "alice"
    assert result.otp == "123456"
    assert result.wg_pubkey == "A" * 44
    assert abs(result.timestamp - int(time.time())) < 5


def test_roundtrip_unicode_uid(server_keypair):
    """uid truncated/padded to 64 bytes — ASCII-safe usernames roundtrip cleanly."""
    _, _, pub_b64 = server_keypair
    priv, _, _ = server_keypair
    pkt = build_packet("bob_user", "000000", "B" * 44, pub_b64)
    result = parse_packet(pkt, server_privkey=priv)
    assert result is not None
    assert result.uid == "bob_user"


def test_roundtrip_long_uid_truncated(server_keypair):
    """uid longer than 64 bytes is truncated at build time."""
    _, _, pub_b64 = server_keypair
    priv, _, _ = server_keypair
    long_uid = "x" * 100
    pkt = build_packet(long_uid, "111111", "C" * 44, pub_b64)
    result = parse_packet(pkt, server_privkey=priv)
    assert result is not None
    assert result.uid == "x" * 64


# ---------------------------------------------------------------------------
# Authentication failures — silent drop (None)
# ---------------------------------------------------------------------------

def test_wrong_server_key(server_keypair, sample_packet):
    """Parsing with a different private key must return None."""
    wrong_priv = X25519PrivateKey.generate()
    result = parse_packet(sample_packet, server_privkey=wrong_priv)
    assert result is None


def test_tampered_ciphertext(server_keypair, sample_packet):
    """Flipping a byte in the ciphertext must fail GCM auth."""
    priv, _, _ = server_keypair
    data = bytearray(sample_packet)
    data[_OFF_NONCE + NONCE_SIZE + 5] ^= 0xFF  # flip a byte in ciphertext
    result = parse_packet(bytes(data), server_privkey=priv)
    assert result is None


def test_tampered_tag(server_keypair, sample_packet):
    """Flipping a byte in the GCM tag must fail authentication."""
    priv, _, _ = server_keypair
    data = bytearray(sample_packet)
    data[_OFF_VER - 1] ^= 0xFF  # last byte of tag
    result = parse_packet(bytes(data), server_privkey=priv)
    assert result is None


def test_tampered_ephemeral_pub(server_keypair, sample_packet):
    """Corrupting the ephemeral public key leads to wrong shared secret → GCM fails."""
    priv, _, _ = server_keypair
    data = bytearray(sample_packet)
    data[0] ^= 0xFF
    result = parse_packet(bytes(data), server_privkey=priv)
    assert result is None


# ---------------------------------------------------------------------------
# Size checks
# ---------------------------------------------------------------------------

def test_too_short(server_keypair):
    priv, _, _ = server_keypair
    assert parse_packet(b"\x00" * 100, server_privkey=priv) is None


def test_too_long(server_keypair):
    priv, _, _ = server_keypair
    assert parse_packet(b"\x00" * 200, server_privkey=priv) is None


def test_empty(server_keypair):
    priv, _, _ = server_keypair
    assert parse_packet(b"", server_privkey=priv) is None


# ---------------------------------------------------------------------------
# Wrong version marker
# ---------------------------------------------------------------------------

def test_wrong_version(server_keypair, sample_packet):
    """A packet with wrong version bytes must be dropped."""
    priv, _, _ = server_keypair
    data = bytearray(sample_packet)
    data[_OFF_VER] = 0x01  # version 1, not 2
    result = parse_packet(bytes(data), server_privkey=priv)
    assert result is None


# ---------------------------------------------------------------------------
# Timestamp skew
# ---------------------------------------------------------------------------

def test_timestamp_skew(server_keypair):
    """A packet with a timestamp > 30 s old must be dropped."""
    _, _, pub_b64 = server_keypair
    priv, _, _ = server_keypair

    # Build a fresh packet then manually patch the timestamp inside the payload.
    # We need to re-encrypt the payload with the correct key, which we can't easily
    # do without knowing the ephemeral key. Instead, verify at the build level that
    # the packet with a fresh timestamp (< 30 s) is accepted and an old one is not.
    # This test patches time.time() to simulate a stale packet being checked later.
    import unittest.mock as mock

    pkt = build_packet("alice", "123456", "A" * 44, pub_b64)

    # Normal time → accepted
    result = parse_packet(pkt, server_privkey=priv)
    assert result is not None

    # 60 seconds in the future → timestamp in packet is now 60 s old → rejected
    with mock.patch("vpn.spa.time") as mock_time:
        mock_time.time.return_value = time.time() + 60
        result = parse_packet(pkt, server_privkey=priv)
    assert result is None


# ---------------------------------------------------------------------------
# Each packet is unique (ephemeral keypair)
# ---------------------------------------------------------------------------

def test_packets_are_unique(server_keypair):
    """Two packets for the same user/otp must differ (ephemeral key randomness)."""
    _, _, pub_b64 = server_keypair
    pkt1 = build_packet("alice", "123456", "A" * 44, pub_b64)
    pkt2 = build_packet("alice", "123456", "A" * 44, pub_b64)
    assert pkt1 != pkt2


# ---------------------------------------------------------------------------
# Module-level keypair (init_server_keypair + get_spa_pubkey_b64)
# ---------------------------------------------------------------------------

def test_module_pubkey_set(server_keypair):
    """After init_server_keypair, get_spa_pubkey_b64 returns a non-empty string."""
    pubkey = get_spa_pubkey_b64()
    assert pubkey
    assert len(__import__("base64").b64decode(pubkey)) == 32  # 32 raw bytes


def test_parse_using_module_keypair(server_keypair):
    """parse_packet without explicit privkey uses module-level _spa_privkey."""
    _, _, pub_b64 = server_keypair
    pkt = build_packet("alice", "999999", "D" * 44, pub_b64)
    result = parse_packet(pkt)  # no explicit privkey
    assert result is not None
    assert result.uid == "alice"
    assert result.otp == "999999"


# ---------------------------------------------------------------------------
# uid_to_ip helper
# ---------------------------------------------------------------------------

def test_uid_to_ip():
    assert uid_to_ip(1, "10.13.13.0/24") == "10.13.13.1"
    assert uid_to_ip(3, "10.13.13.0/24") == "10.13.13.3"
    assert uid_to_ip(2, "10.8.0.0/24") == "10.8.0.2"
