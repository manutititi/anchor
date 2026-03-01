"""
OTP seed management and vpn_uid assignment for the SPA flow.

assign_vpn_uid:   atomically assign the next available UID to a user.
                  UID=1 is reserved for the WireGuard server; user UIDs start at 2.
generate_otp_seed: create a new TOTP seed, encrypt it, store in users collection.
get_otp_seed:     decrypt and return the plaintext seed for a user.
verify_otp:       validate a 6-digit TOTP code (valid_window=1, ±30 s).
"""
import pyotp

from core.utils import now_tz
from db.client import get_collection
from vault.crypto import decrypt, encrypt


def assign_vpn_uid(username: str) -> int:
    """
    Atomically assign the next available VPN UID to username.
    Uses a MongoDB counter document so concurrent requests are safe.
    Returns the assigned integer UID (≥ 2; UID=1 is the WireGuard server).
    """
    counter_doc = get_collection("vpn_uid_counter").find_one_and_update(
        {"_id": "vpn_uid"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    # seq starts at 0 on first upsert; +1 → first user gets UID=2
    uid = counter_doc["seq"] + 1

    get_collection("users").update_one(
        {"username": username},
        {"$set": {"vpn_uid": uid, "vpn_uid_assigned_at": now_tz().isoformat()}},
    )
    return uid


def generate_otp_seed(username: str) -> str:
    """
    Generate a new TOTP seed for username, encrypt it with the vault master key,
    and persist in the users collection under otp_seed_enc.
    Returns the plaintext base32 seed (shown to the user/admin once for setup).
    """
    seed = pyotp.random_base32()
    encrypted = encrypt(seed, f"vpn-otp/{username}")
    get_collection("users").update_one(
        {"username": username},
        {"$set": {"otp_seed_enc": encrypted}},
    )
    return seed


def get_otp_seed(username: str) -> str | None:
    """Return the plaintext TOTP seed for username, or None if not configured."""
    doc = get_collection("users").find_one(
        {"username": username}, {"otp_seed_enc": 1}
    )
    if not doc or "otp_seed_enc" not in doc:
        return None
    return decrypt(doc["otp_seed_enc"], f"vpn-otp/{username}")


def verify_otp(username: str, otp_str: str) -> bool:
    """Validate a 6-digit TOTP code against the user's seed. valid_window=1 (±30 s)."""
    seed = get_otp_seed(username)
    if not seed:
        return False
    return bool(pyotp.TOTP(seed).verify(otp_str, valid_window=1))
