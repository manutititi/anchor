"""
Knock listener lease handling tests — mocks MongoDB and sidecar.

Run from server/code/ with rootdir set:
  PYTHONPATH=. python -m pytest tests/test_knock_lease.py -v --rootdir=.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Stub heavy server dependencies before any server module is imported.
# This lets knock.py (and its transitive deps) import without needing
# a live MongoDB, pyotp, or passlib installation.
# ---------------------------------------------------------------------------
import types

def _stub_module(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules.setdefault(name, m)
    return m

# pymongo
_pymongo = _stub_module("pymongo",
    MongoClient=mock.MagicMock(),
    ReturnDocument=mock.MagicMock(),
)
_pymongo_errors = _stub_module("pymongo.errors",
    DuplicateKeyError=type("DuplicateKeyError", (Exception,), {}),
    OperationFailure=type("OperationFailure", (Exception,), {}),
)
_pymongo.errors = _pymongo_errors

# pyotp
_pyotp = _stub_module("pyotp",
    TOTP=mock.MagicMock(),
    random_base32=mock.MagicMock(return_value="JBSWY3DPEHPK3PXP"),
)

# passlib / bcrypt (pulled in by auth modules)
_stub_module("passlib")
_stub_module("passlib.context", CryptContext=mock.MagicMock())
_stub_module("bcrypt")

# vault.crypto
_vault_crypto = _stub_module("vault.crypto",
    encrypt=mock.MagicMock(return_value={"value": "x", "iv": "y", "tag": "z", "encoding": "aes256-gcm-hkdf"}),
    decrypt=mock.MagicMock(return_value="plaintext_seed"),
)
_stub_module("vault", crypto=_vault_crypto)

# db.client — get_collection will be patched per-test
_db_client = _stub_module("db.client",
    get_collection=mock.MagicMock(),
    get_client=mock.MagicMock(),
    close_client=mock.MagicMock(),
)
_stub_module("db", client=_db_client)

# core.utils
_stub_module("core.utils", now_tz=mock.MagicMock(return_value="2026-01-01T00:00:00Z"))
_stub_module("core")

# We need the SPA keypair initialized before importing knock
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
import base64


@pytest.fixture(scope="module", autouse=True)
def init_keypair():
    from vpn.spa import init_server_keypair
    priv = X25519PrivateKey.generate()
    priv_b64 = base64.b64encode(
        priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    ).decode()
    init_server_keypair(priv_b64)


def _make_protocol(subnet="10.13.13.0/24"):
    from vpn.knock import KnockProtocol
    return KnockProtocol(subnet)


def _make_spa_packet(uid="testuser", otp="123456", wg_pubkey=None):
    """Build a valid SPA v2 packet using the initialized module keypair."""
    from vpn.spa import build_packet, get_spa_pubkey_b64
    wg_pubkey = wg_pubkey or "A" * 44
    return build_packet(uid, otp, wg_pubkey, get_spa_pubkey_b64())


# ---------------------------------------------------------------------------
# Helper: build a mock MongoDB collection
# ---------------------------------------------------------------------------

def _mongo_col(docs=None):
    """Return a mock collection with the given initial documents."""
    docs = list(docs or [])
    col = mock.MagicMock()
    col.find_one.return_value = docs[0] if docs else None
    col.insert_one.return_value = mock.MagicMock()
    col.delete_one.return_value = mock.MagicMock()
    return col


# ---------------------------------------------------------------------------
# Test: no existing lease → create onboarding lease
# ---------------------------------------------------------------------------

def test_no_existing_lease_creates_onboarding():
    protocol = _make_protocol()
    pkt = _make_spa_packet()

    with (
        mock.patch("vpn.knock.parse_packet") as mock_parse,
        mock.patch("vpn.knock.verify_otp", return_value=True),
        mock.patch("vpn.knock.get_collection") as mock_gc,
        mock.patch("integrations.wireguard.provider.WireGuardProvider") as mock_wg,
    ):
        from vpn.spa import SPAData
        mock_parse.return_value = SPAData(
            uid="testuser", otp="123456", timestamp=int(time.time()), wg_pubkey="A" * 44
        )

        nonces_col = mock.MagicMock()
        nonces_col.insert_one.return_value = None
        users_col = mock.MagicMock()
        users_col.find_one.return_value = {"vpn_uid": 5}
        leases_col = mock.MagicMock()
        leases_col.find_one.return_value = None  # no existing lease

        def _get_col(name):
            return {"vpn_nonces": nonces_col, "users": users_col, "vpn_leases": leases_col}[name]

        mock_gc.side_effect = _get_col

        mock_client = mock.MagicMock()
        mock_wg.return_value.get_client.return_value = mock_client

        protocol._process(pkt, ("1.2.3.4", 5000))

        # Peer registered on sidecar
        mock_client.add_peer.assert_called_once()
        args = mock_client.add_peer.call_args[0]
        assert args[0] == "A" * 44  # wg_pubkey
        assert args[1] == "10.13.13.5"  # uid_to_ip(5, "10.13.13.0/24")

        # Onboarding lease inserted
        leases_col.insert_one.assert_called_once()
        doc = leases_col.insert_one.call_args[0][0]
        assert doc["uid"] == "testuser"
        assert doc["state"] == "onboarding"
        assert doc["pubkey"] == "A" * 44


# ---------------------------------------------------------------------------
# Test: stale onboarding lease → clean up + re-register
# ---------------------------------------------------------------------------

def test_stale_onboarding_lease_is_replaced():
    protocol = _make_protocol()

    old_pubkey = "B" * 44
    existing_lease = {"uid": "testuser", "state": "onboarding", "pubkey": old_pubkey}

    with (
        mock.patch("vpn.knock.parse_packet") as mock_parse,
        mock.patch("vpn.knock.verify_otp", return_value=True),
        mock.patch("vpn.knock.get_collection") as mock_gc,
        mock.patch("integrations.wireguard.provider.WireGuardProvider") as mock_wg,
    ):
        from vpn.spa import SPAData
        new_pubkey = "C" * 44
        mock_parse.return_value = SPAData(
            uid="testuser", otp="654321", timestamp=int(time.time()), wg_pubkey=new_pubkey
        )

        nonces_col = mock.MagicMock()
        users_col = mock.MagicMock()
        users_col.find_one.return_value = {"vpn_uid": 3}
        leases_col = mock.MagicMock()
        leases_col.find_one.return_value = existing_lease

        mock_gc.side_effect = lambda name: {
            "vpn_nonces": nonces_col, "users": users_col, "vpn_leases": leases_col
        }[name]

        mock_client = mock.MagicMock()
        mock_wg.return_value.get_client.return_value = mock_client

        protocol._process(b"\x00" * 186, ("1.2.3.4", 5000))

        # Old peer removed
        mock_client.remove_peer.assert_called_once_with(old_pubkey)
        # Old lease deleted
        leases_col.delete_one.assert_called_once_with({"uid": "testuser"})
        # New peer added with new pubkey
        add_args = mock_client.add_peer.call_args[0]
        assert add_args[0] == new_pubkey
        # New onboarding lease created
        doc = leases_col.insert_one.call_args[0][0]
        assert doc["state"] == "onboarding"
        assert doc["pubkey"] == new_pubkey


# ---------------------------------------------------------------------------
# Test: active (non-expired) lease → allowed to re-knock (lease renewal)
# ---------------------------------------------------------------------------

def test_active_lease_allows_re_knock():
    protocol = _make_protocol()

    old_pubkey = "D" * 44
    existing_lease = {
        "uid": "testuser",
        "state": "active",
        "pubkey": old_pubkey,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }

    with (
        mock.patch("vpn.knock.parse_packet") as mock_parse,
        mock.patch("vpn.knock.verify_otp", return_value=True),
        mock.patch("vpn.knock.get_collection") as mock_gc,
        mock.patch("integrations.wireguard.provider.WireGuardProvider") as mock_wg,
    ):
        from vpn.spa import SPAData
        new_pubkey = "E" * 44
        mock_parse.return_value = SPAData(
            uid="testuser", otp="000000", timestamp=int(time.time()), wg_pubkey=new_pubkey
        )

        nonces_col = mock.MagicMock()
        users_col = mock.MagicMock()
        users_col.find_one.return_value = {"vpn_uid": 4}
        leases_col = mock.MagicMock()
        leases_col.find_one.return_value = existing_lease

        mock_gc.side_effect = lambda name: {
            "vpn_nonces": nonces_col, "users": users_col, "vpn_leases": leases_col
        }[name]

        mock_client = mock.MagicMock()
        mock_wg.return_value.get_client.return_value = mock_client

        protocol._process(b"\x00" * 186, ("1.2.3.4", 5000))

        # Old peer removed (not blocked just because lease was active)
        mock_client.remove_peer.assert_called_once_with(old_pubkey)
        # Old lease deleted
        leases_col.delete_one.assert_called_once()
        # New peer added
        mock_client.add_peer.assert_called_once()
        # New onboarding lease
        doc = leases_col.insert_one.call_args[0][0]
        assert doc["state"] == "onboarding"
        assert doc["pubkey"] == new_pubkey


# ---------------------------------------------------------------------------
# Test: replay attack — duplicate nonce → drop
# ---------------------------------------------------------------------------

def test_replay_attack_dropped():
    protocol = _make_protocol()

    with (
        mock.patch("vpn.knock.parse_packet") as mock_parse,
        mock.patch("vpn.knock.verify_otp", return_value=True),
        mock.patch("vpn.knock.get_collection") as mock_gc,
        mock.patch("integrations.wireguard.provider.WireGuardProvider") as mock_wg,
    ):
        from vpn.spa import SPAData
        mock_parse.return_value = SPAData(
            uid="testuser", otp="111111", timestamp=int(time.time()), wg_pubkey="A" * 44
        )

        nonces_col = mock.MagicMock()
        # Simulate duplicate key error (nonce already seen)
        from pymongo.errors import DuplicateKeyError
        nonces_col.insert_one.side_effect = DuplicateKeyError("duplicate nonce")
        users_col = mock.MagicMock()
        leases_col = mock.MagicMock()

        mock_gc.side_effect = lambda name: {
            "vpn_nonces": nonces_col, "users": users_col, "vpn_leases": leases_col
        }[name]

        mock_client = mock.MagicMock()
        mock_wg.return_value.get_client.return_value = mock_client

        protocol._process(b"\x00" * 186, ("1.2.3.4", 5000))

        # Sidecar must NOT be called — packet dropped at nonce check
        mock_client.add_peer.assert_not_called()
        leases_col.insert_one.assert_not_called()


# ---------------------------------------------------------------------------
# Test: OTP failure → drop
# ---------------------------------------------------------------------------

def test_otp_failure_drops_packet():
    protocol = _make_protocol()

    with (
        mock.patch("vpn.knock.parse_packet") as mock_parse,
        mock.patch("vpn.knock.verify_otp", return_value=False),  # OTP fails
        mock.patch("vpn.knock.get_collection") as mock_gc,
        mock.patch("integrations.wireguard.provider.WireGuardProvider") as mock_wg,
    ):
        from vpn.spa import SPAData
        mock_parse.return_value = SPAData(
            uid="testuser", otp="wrong1", timestamp=int(time.time()), wg_pubkey="A" * 44
        )

        nonces_col = mock.MagicMock()
        users_col = mock.MagicMock()
        leases_col = mock.MagicMock()

        mock_gc.side_effect = lambda name: {
            "vpn_nonces": nonces_col, "users": users_col, "vpn_leases": leases_col
        }[name]

        mock_client = mock.MagicMock()
        mock_wg.return_value.get_client.return_value = mock_client

        protocol._process(b"\x00" * 186, ("1.2.3.4", 5000))

        mock_client.add_peer.assert_not_called()
        leases_col.insert_one.assert_not_called()


# ---------------------------------------------------------------------------
# Test: unknown uid → drop
# ---------------------------------------------------------------------------

def test_unknown_uid_drops_packet():
    protocol = _make_protocol()

    with (
        mock.patch("vpn.knock.parse_packet") as mock_parse,
        mock.patch("vpn.knock.verify_otp", return_value=True),
        mock.patch("vpn.knock.get_collection") as mock_gc,
        mock.patch("integrations.wireguard.provider.WireGuardProvider") as mock_wg,
    ):
        from vpn.spa import SPAData
        mock_parse.return_value = SPAData(
            uid="ghost", otp="123456", timestamp=int(time.time()), wg_pubkey="A" * 44
        )

        nonces_col = mock.MagicMock()
        users_col = mock.MagicMock()
        users_col.find_one.return_value = None  # user not found
        leases_col = mock.MagicMock()

        mock_gc.side_effect = lambda name: {
            "vpn_nonces": nonces_col, "users": users_col, "vpn_leases": leases_col
        }[name]

        mock_client = mock.MagicMock()
        mock_wg.return_value.get_client.return_value = mock_client

        protocol._process(b"\x00" * 186, ("1.2.3.4", 5000))

        mock_client.add_peer.assert_not_called()
        leases_col.insert_one.assert_not_called()
