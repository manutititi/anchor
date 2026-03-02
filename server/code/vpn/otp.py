"""
OTP seed management and vpn_uid assignment for the SPA flow.

assign_vpn_uid:   atomically assign the next available UID to a user.
                  uid=1 = WireGuard server, uid=2 = static admin peer (peer1).
                  Dynamic users start at DYNAMIC_UID_MIN (3).
generate_otp_seed: create a new TOTP seed, encrypt it, store in users collection.
get_otp_seed:     decrypt and return the plaintext seed for a user.
verify_otp:       validate a 6-digit TOTP code (valid_window=1, ±30 s).
"""
import pyotp

from core.utils import now_tz
from db.client import get_collection
from vault.crypto import decrypt, encrypt

# UIDs below this value are reserved:
#   uid=1 → WireGuard server (10.x.x.1)
#   uid=2 → static admin backdoor peer / linuxserver PEERS=peer1 (10.x.x.2)
DYNAMIC_UID_MIN = 3


def assign_vpn_uid(username: str) -> int:
    """
    Return the existing VPN UID for username, or atomically assign the next one.
    Existing UIDs below DYNAMIC_UID_MIN are treated as stale (reserved range)
    and replaced with a fresh assignment from the counter.
    """
    # Reuse existing uid on re-provision so the IP stays stable —
    # but only if it falls in the valid dynamic range.
    user_doc = get_collection("users").find_one({"username": username}, {"vpn_uid": 1})
    if user_doc and user_doc.get("vpn_uid"):
        existing = int(user_doc["vpn_uid"])
        if existing >= DYNAMIC_UID_MIN:
            return existing
        # Stale uid in the reserved range (e.g. uid=2 assigned before peer1
        # reservation was introduced). Clear it and fall through to assign a
        # fresh one from the counter.
        get_collection("users").update_one(
            {"username": username},
            {"$unset": {"vpn_uid": "", "vpn_uid_assigned_at": ""}},
        )

    # Atomically get the next counter value.
    # init-mongo.js seeds seq=1 so the first $inc → seq=2 → uid=3.
    from pymongo import ReturnDocument
    counter_doc = get_collection("vpn_uid_counter").find_one_and_update(
        {"_id": "vpn_uid"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    uid = int(counter_doc["seq"]) + 1

    # Ensure we never hand out a reserved uid (safety net for edge cases
    # where the counter itself starts at an unexpected value).
    if uid < DYNAMIC_UID_MIN:
        # Force the counter past the reserved range and retry.
        get_collection("vpn_uid_counter").update_one(
            {"_id": "vpn_uid"},
            {"$set": {"seq": DYNAMIC_UID_MIN - 1}},
        )
        counter_doc = get_collection("vpn_uid_counter").find_one_and_update(
            {"_id": "vpn_uid"},
            {"$inc": {"seq": 1}},
            return_document=ReturnDocument.AFTER,
        )
        uid = int(counter_doc["seq"]) + 1

    get_collection("users").update_one(
        {"username": username},
        {"$set": {"vpn_uid": uid, "vpn_uid_assigned_at": now_tz()}},
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
