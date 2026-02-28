"""
Integration configuration store — MongoDB-backed, sensitive fields encrypted
with the same AES-256-GCM + HKDF mechanism used by the vault.

Encryption key derivation context: "integration:<type>:<field>"
This gives each sensitive field its own derived key, independent of vault secrets.
"""
from datetime import datetime
from typing import Optional
from db.client import get_collection
from vault.crypto import encrypt, decrypt

COLLECTION = "integrations"
_CONTEXT_PREFIX = "integration"


def _secret_id(integration_type: str, field: str) -> str:
    return f"{_CONTEXT_PREFIX}:{integration_type}:{field}"


def _is_encrypted_blob(value) -> bool:
    return isinstance(value, dict) and value.get("encoding") == "aes256-gcm-hkdf"


def _encrypt_config(integration_type: str, config: dict, encrypted_fields: list[str]) -> dict:
    result = {}
    for k, v in config.items():
        if k in encrypted_fields and isinstance(v, str) and v and not _is_encrypted_blob(v):
            result[k] = encrypt(v, _secret_id(integration_type, k))
        else:
            result[k] = v
    return result


def _decrypt_config(integration_type: str, config: dict, encrypted_fields: list[str]) -> dict:
    result = {}
    for k, v in config.items():
        if k in encrypted_fields and _is_encrypted_blob(v):
            result[k] = decrypt(v, _secret_id(integration_type, k))
        else:
            result[k] = v
    return result


def _mask_config(config: dict, encrypted_fields: list[str]) -> dict:
    return {k: ("***" if k in encrypted_fields else v) for k, v in config.items()}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_config(
    integration_type: str,
    config: dict,
    encrypted_fields: list[str],
    created_by: str,
) -> None:
    """Upsert an integration config. Sensitive fields are encrypted before storing."""
    col = get_collection(COLLECTION)
    stored_config = _encrypt_config(integration_type, config, encrypted_fields)
    now = datetime.utcnow().isoformat()

    existing = col.find_one({"_id": integration_type})
    if existing:
        col.update_one(
            {"_id": integration_type},
            {"$set": {
                "config": stored_config,
                "encrypted_fields": encrypted_fields,
                "updated_at": now,
            }},
        )
    else:
        col.insert_one({
            "_id": integration_type,
            "type": integration_type,
            "config": stored_config,
            "encrypted_fields": encrypted_fields,
            "created_at": now,
            "updated_at": now,
            "created_by": created_by,
        })


def get_config(integration_type: str) -> Optional[dict]:
    """Return the decrypted config dict, or None if not configured."""
    col = get_collection(COLLECTION)
    doc = col.find_one({"_id": integration_type})
    if not doc:
        return None
    encrypted_fields = doc.get("encrypted_fields", [])
    return _decrypt_config(integration_type, doc.get("config", {}), encrypted_fields)


def get_masked_config(integration_type: str) -> Optional[dict]:
    """Return config with sensitive fields replaced by '***' (safe for API responses)."""
    col = get_collection(COLLECTION)
    doc = col.find_one({"_id": integration_type})
    if not doc:
        return None
    encrypted_fields = doc.get("encrypted_fields", [])
    return _mask_config(doc.get("config", {}), encrypted_fields)


def get_metadata(integration_type: str) -> Optional[dict]:
    """Return integration metadata without the config blob."""
    col = get_collection(COLLECTION)
    doc = col.find_one({"_id": integration_type}, {"config": 0})
    if not doc:
        return None
    return {
        "type": doc.get("type", integration_type),
        "encrypted_fields": doc.get("encrypted_fields", []),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "created_by": doc.get("created_by"),
    }


def delete_config(integration_type: str) -> bool:
    """Remove an integration config. Returns True if something was deleted."""
    result = get_collection(COLLECTION).delete_one({"_id": integration_type})
    return result.deleted_count > 0


def list_configs() -> list[dict]:
    """Return metadata for all stored integrations (no config, no sensitive data)."""
    results = []
    for doc in get_collection(COLLECTION).find({}, {"config": 0}):
        results.append({
            "type": doc.get("type", doc["_id"]),
            "encrypted_fields": doc.get("encrypted_fields", []),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "created_by": doc.get("created_by"),
        })
    return results
