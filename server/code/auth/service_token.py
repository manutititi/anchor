import secrets
import hashlib
from datetime import datetime
from fastapi import HTTPException
from bson import ObjectId
from db.client import get_collection
from core.utils import now_tz

VALID_SCOPES = {"vault:read", "vault:write", "anchors:read", "anchors:write", "admin"}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_service_token(
    name: str,
    scopes: list[str],
    created_by: str,
    expires_at: datetime | None = None,
) -> str:
    invalid = set(scopes) - VALID_SCOPES
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid scopes: {sorted(invalid)}")

    raw_token = "anc_" + secrets.token_urlsafe(32)
    col = get_collection("service_tokens")
    col.insert_one({
        "name": name,
        "token_hash": _hash_token(raw_token),
        "scopes": scopes,
        "created_by": created_by,
        "created_at": now_tz(),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "last_used": None,
        "active": True,
    })
    return raw_token


def validate_service_token(token: str) -> dict | None:
    col = get_collection("service_tokens")
    token_hash = _hash_token(token)
    doc = col.find_one({"token_hash": token_hash, "active": True})
    if not doc:
        return None
    if doc.get("expires_at") and doc["expires_at"] < now_tz():
        return None
    col.update_one({"token_hash": token_hash}, {"$set": {"last_used": now_tz()}})
    return {"name": doc["name"], "scopes": doc["scopes"]}


def revoke_service_token(token_id: str):
    col = get_collection("service_tokens")
    result = col.update_one({"_id": ObjectId(token_id)}, {"$set": {"active": False}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Token not found")


def list_service_tokens() -> list[dict]:
    col = get_collection("service_tokens")
    docs = col.find({}, {"token_hash": 0})
    result = []
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
        result.append(doc)
    return result
