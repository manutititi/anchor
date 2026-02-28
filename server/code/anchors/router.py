import re
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import JSONResponse
from collections import OrderedDict
from auth.middleware import get_current_user, get_current_groups, get_current_scopes
from db.client import get_collection
from core.filter import query_collection
from core.utils import now_tz
from core.logger import LogEntry
from anchors import access

router = APIRouter()

_SECRET_REF = re.compile(r'\[\[secret:([^\]]+)\]\]')


# ---------------------------------------------------------------------------
# Secret-link helpers
# ---------------------------------------------------------------------------

def _extract_secret_refs(doc: dict) -> list[str]:
    """Find all [[secret:X]] paths in any string field of an anchor doc."""
    refs: set[str] = set()
    for v in doc.values():
        if isinstance(v, str):
            refs.update(_SECRET_REF.findall(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    refs.update(_SECRET_REF.findall(item))
                elif isinstance(item, dict):
                    for vv in item.values():
                        if isinstance(vv, str):
                            refs.update(_SECRET_REF.findall(vv))
    return sorted(refs)


def _sync_secret_permissions(
    anchor_name: str,
    secret_paths: list[str],
    groups: list,
    users: list,
) -> None:
    """Set anchor_link and sync groups/users to linked secrets."""
    if not secret_paths:
        return
    col = get_collection("ref")
    col.update_many(
        {"id": {"$in": secret_paths}},
        {"$set": {"anchor_link": anchor_name, "groups": groups, "users": users}},
    )


def _clear_secret_links(secret_paths: list[str]) -> None:
    """Remove anchor_link from secrets no longer referenced."""
    if not secret_paths:
        return
    col = get_collection("ref")
    col.update_many(
        {"id": {"$in": secret_paths}},
        {"$unset": {"anchor_link": ""}},
    )


# ---------------------------------------------------------------------------
# List anchors
# ---------------------------------------------------------------------------

@router.get("", tags=["anchors"])
def list_anchors(
    filter: str = Query(default=""),
    user: str = Depends(get_current_user),
    user_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    projection = {
        "_id": 0, "name": 1, "type": 1, "path": 1, "note": 1,
        "groups": 1, "meta": 1, "project": 1, "env": 1,
        "last_updated": 1, "updated_by": 1, "created_by": 1,
        "host": 1, "user": 1, "port": 1, "routes": 1,
        "users": 1, "allow_group_edit": 1, "linked_secrets": 1,
    }
    anchors = query_collection("anchors", filter, projection)
    visibles = [
        a for a in anchors
        if access.is_visible(a, user, user_groups, current_scopes)
    ]
    return JSONResponse(content=visibles)


# ---------------------------------------------------------------------------
# Get anchor
# ---------------------------------------------------------------------------

@router.get("/{name}", tags=["anchors"])
def get_anchor(
    name: str,
    user: str = Depends(get_current_user),
    user_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    col = get_collection("anchors")
    anchor = col.find_one({"name": name}, {"_id": 0})
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")
    if not access.is_visible(anchor, user, user_groups, current_scopes):
        raise HTTPException(status_code=403, detail="Access denied")
    return JSONResponse(content=anchor)


# ---------------------------------------------------------------------------
# Create / upsert anchor
# ---------------------------------------------------------------------------

@router.post("", tags=["anchors"])
async def upsert_anchor(
    request: Request,
    user: str = Depends(get_current_user),
):
    data = await request.json()
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="Missing required field: name")
    if not data.get("type"):
        raise HTTPException(status_code=400, detail="Missing required field: type")

    col = get_collection("anchors")
    name = data["name"]
    existing = col.find_one({"name": name})
    now = now_tz()

    if not existing:
        data["created_at"] = now
        data["created_by"] = user
        data.setdefault("users", [])
        data.setdefault("allow_group_edit", False)

    data["last_updated"] = now
    data["updated_by"] = user

    # Extract and store secret references
    secret_refs = _extract_secret_refs(data)
    old_refs = existing.get("linked_secrets", []) if existing else []
    data["linked_secrets"] = secret_refs

    reordered = OrderedDict()
    for key in ("type", "name", "groups"):
        if key in data:
            reordered[key] = data[key]
    for k, v in data.items():
        if k not in reordered:
            reordered[k] = v

    col.replace_one({"name": name}, reordered, upsert=True)

    # Sync link + permissions to referenced secrets
    if secret_refs:
        _sync_secret_permissions(
            name, secret_refs,
            list(data.get("groups", [])),
            list(data.get("users", [])),
        )
    removed_refs = [r for r in old_refs if r not in secret_refs]
    if removed_refs:
        _clear_secret_links(removed_refs)

    action = "create" if not existing else "update"
    response = JSONResponse(content={"status": "ok", "anchor": name, "user": user})
    LogEntry.from_request(
        request=request, response=response,
        resource="anchor", resource_id=name,
        action=action, success=True,
        extra={"anchor_type": data.get("type")},
    ).save_default()
    return response


# ---------------------------------------------------------------------------
# Patch anchor (partial update)
# ---------------------------------------------------------------------------

@router.patch("/{name}", tags=["anchors"])
async def patch_anchor(
    name: str,
    request: Request,
    user: str = Depends(get_current_user),
    user_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    col = get_collection("anchors")
    existing = col.find_one({"name": name}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Anchor not found")

    data = await request.json()

    # ACL fields require can_manage_acl; all others just require can_edit
    acl_fields = {"groups", "users", "allow_group_edit", "transfer_to"}
    has_acl = bool(acl_fields & data.keys())

    if has_acl:
        if not access.can_manage_acl(existing, user, user_groups, current_scopes):
            raise HTTPException(
                status_code=403,
                detail="Only the creator or admins can change access rules",
            )
    else:
        if not access.can_edit(existing, user, user_groups, current_scopes):
            raise HTTPException(
                status_code=403,
                detail="Access denied: insufficient permissions to edit this anchor",
            )

    # Strip immutable fields
    for field in ("name", "type", "created_by", "created_at"):
        data.pop(field, None)

    # Handle ownership transfer
    if "transfer_to" in data:
        data["created_by"] = data.pop("transfer_to")

    data["last_updated"] = now_tz()
    data["updated_by"] = user

    # Re-extract secret refs from merged doc
    merged = {**existing, **data}
    new_refs = _extract_secret_refs(merged)
    old_refs = existing.get("linked_secrets", [])
    refs_changed = new_refs != old_refs
    if refs_changed:
        data["linked_secrets"] = new_refs
        removed_refs = [r for r in old_refs if r not in new_refs]
        if removed_refs:
            _clear_secret_links(removed_refs)

    col.update_one({"name": name}, {"$set": data})

    # Sync permissions to linked secrets automatically
    final_groups = list(merged.get("groups", []))
    final_users = list(merged.get("users", []))
    if has_acl:
        # ACL changed → push to ALL current linked secrets
        final_linked = new_refs if refs_changed else old_refs
        _sync_secret_permissions(name, final_linked, final_groups, final_users)
    elif refs_changed:
        # Only new refs added (no ACL change) → sync current anchor perms to new refs
        newly_added = [r for r in new_refs if r not in old_refs]
        _sync_secret_permissions(name, newly_added, final_groups, final_users)
    response = JSONResponse(content={"status": "ok", "anchor": name})
    LogEntry.from_request(
        request=request, response=response,
        resource="anchor", resource_id=name,
        action="update", success=True,
    ).save_default()
    return response


# ---------------------------------------------------------------------------
# Delete anchor
# ---------------------------------------------------------------------------

@router.delete("/{name}", tags=["anchors"])
def delete_anchor(
    name: str,
    request: Request,
    user: str = Depends(get_current_user),
    user_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
    delete_secrets: bool = Query(False),
):
    col = get_collection("anchors")
    existing = col.find_one({"name": name}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Anchor not found")
    if not access.can_delete(existing, user, user_groups, current_scopes):
        raise HTTPException(
            status_code=403,
            detail="Only the creator or admins can delete this anchor",
        )

    linked_secrets = existing.get("linked_secrets", [])
    col.delete_one({"name": name})

    if delete_secrets and linked_secrets:
        ref_col = get_collection("ref")
        ref_col.delete_many({"id": {"$in": linked_secrets}})
    elif linked_secrets:
        _clear_secret_links(linked_secrets)

    response = JSONResponse(content={"status": "deleted", "anchor": name})
    LogEntry.from_request(
        request=request, response=response,
        resource="anchor", resource_id=name,
        action="delete", success=True,
        extra={
            "cascade_secrets": delete_secrets,
            "linked_secrets": linked_secrets,
        },
    ).save_default()
    return response


# ---------------------------------------------------------------------------
# Backward-compatible /db/... aliases (for existing CLI push/pull)
# ---------------------------------------------------------------------------

compat_router = APIRouter(tags=["db (deprecated)"])


@compat_router.post("/db/upload/{filename}")
async def compat_upload(
    filename: str,
    request: Request,
    user: str = Depends(get_current_user),
):
    data = await request.json()
    if "name" not in data or not data["name"]:
        data["name"] = filename.rsplit(".", 1)[0]

    col = get_collection("anchors")
    name = data["name"]
    existing = col.find_one({"name": name})
    now = now_tz()

    if not existing:
        data["created_at"] = now
        data["created_by"] = user

    data["last_updated"] = now
    data["updated_by"] = user

    reordered = OrderedDict()
    for key in ("type", "name", "groups"):
        if key in data:
            reordered[key] = data[key]
    for k, v in data.items():
        if k not in reordered:
            reordered[k] = v

    result = col.replace_one({"name": name}, reordered, upsert=True)
    return JSONResponse(content={
        "status": "ok",
        "anchor": name,
        "inserted": result.upserted_id is not None,
        "user": user,
    })


@compat_router.get("/db/list")
def compat_list(
    filter: str = "",
    user: str = Depends(get_current_user),
    user_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    projection = {
        "_id": 0, "name": 1, "type": 1, "path": 1, "note": 1,
        "groups": 1, "meta": 1, "project": 1, "env": 1,
        "last_updated": 1, "updated_by": 1, "users": 1, "created_by": 1,
    }
    anchors = query_collection("anchors", filter, projection)
    visibles = [
        a for a in anchors
        if access.is_visible(a, user, user_groups, current_scopes)
    ]
    return JSONResponse(content=visibles)


@compat_router.get("/db/pull/{name}")
def compat_pull(
    name: str,
    user: str = Depends(get_current_user),
    user_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    col = get_collection("anchors")
    anchor = col.find_one({"name": name}, {"_id": 0})
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")
    if not access.is_visible(anchor, user, user_groups, current_scopes):
        raise HTTPException(status_code=403, detail="Access denied")
    return JSONResponse(content=anchor)
