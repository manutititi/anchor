from db.client import get_collection
from core.utils import now_tz

MAX_VERSIONS = 10


def save_version(secret_id: str, encrypted_payload: dict, version_num: int, updated_by: str):
    col = get_collection("secret_versions")
    col.insert_one({
        "secret_id": secret_id,
        "version": version_num,
        "updated_by": updated_by,
        "timestamp": now_tz(),
        "value": encrypted_payload["value"],
        "iv": encrypted_payload["iv"],
        "tag": encrypted_payload["tag"],
        "encoding": encrypted_payload.get("encoding", "aes256-gcm-hkdf"),
    })
    # Prune old versions beyond MAX_VERSIONS
    all_versions = list(
        col.find({"secret_id": secret_id}, {"_id": 1, "version": 1})
        .sort("version", -1)
    )
    if len(all_versions) > MAX_VERSIONS:
        ids_to_delete = [v["_id"] for v in all_versions[MAX_VERSIONS:]]
        col.delete_many({"_id": {"$in": ids_to_delete}})


def get_version(secret_id: str, version: int) -> dict | None:
    col = get_collection("secret_versions")
    return col.find_one({"secret_id": secret_id, "version": version}, {"_id": 0})


def list_versions(secret_id: str) -> list[dict]:
    col = get_collection("secret_versions")
    return list(
        col.find(
            {"secret_id": secret_id},
            {"_id": 0, "secret_id": 0},
        ).sort("version", -1)
    )
