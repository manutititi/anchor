from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import JSONResponse
from collections import OrderedDict
from auth.middleware import get_current_user, get_current_groups
from db.client import get_collection
from core.filter import query_collection
from core.utils import now_tz
from core.logger import LogEntry

router = APIRouter()


def _is_visible(anchor: dict, user_groups: list[str]) -> bool:
    if "admins" in user_groups:
        return True
    groups = anchor.get("groups", [])
    return not groups or "all" in groups or any(g in user_groups for g in groups)


# ---------------------------------------------------------------------------
# List anchors
# ---------------------------------------------------------------------------

@router.get("", tags=["anchors"])
def list_anchors(
    filter: str = Query(default=""),
    user_groups: list[str] = Depends(get_current_groups),
):
    projection = {
        "_id": 0, "name": 1, "type": 1, "path": 1, "note": 1,
        "groups": 1, "meta": 1, "project": 1, "env": 1,
        "last_updated": 1, "updated_by": 1, "created_by": 1,
        "host": 1, "user": 1, "port": 1, "routes": 1,
    }
    anchors = query_collection("anchors", filter, projection)
    visibles = [a for a in anchors if _is_visible(a, user_groups)]
    return JSONResponse(content=visibles)


# ---------------------------------------------------------------------------
# Get anchor
# ---------------------------------------------------------------------------

@router.get("/{name}", tags=["anchors"])
def get_anchor(
    name: str,
    user_groups: list[str] = Depends(get_current_groups),
):
    col = get_collection("anchors")
    anchor = col.find_one({"name": name}, {"_id": 0})
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")
    if not _is_visible(anchor, user_groups):
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

    data["last_updated"] = now
    data["updated_by"] = user

    reordered = OrderedDict()
    for key in ("type", "name", "groups"):
        if key in data:
            reordered[key] = data[key]
    for k, v in data.items():
        if k not in reordered:
            reordered[k] = v

    col.replace_one({"name": name}, reordered, upsert=True)
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
# Patch anchor (partial update — creator or admin only for groups field)
# ---------------------------------------------------------------------------

@router.patch("/{name}", tags=["anchors"])
async def patch_anchor(
    name: str,
    request: Request,
    user: str = Depends(get_current_user),
    user_groups: list[str] = Depends(get_current_groups),
):
    col = get_collection("anchors")
    existing = col.find_one({"name": name}, {"_id": 0, "created_by": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Anchor not found")

    data = await request.json()

    # groups can only be changed by creator or admin
    if "groups" in data and existing.get("created_by") != user and "admins" not in user_groups:
        raise HTTPException(status_code=403, detail="Only the creator or admins can change groups")

    # Strip immutable fields
    for field in ("name", "type", "created_by", "created_at"):
        data.pop(field, None)

    data["last_updated"] = now_tz()
    data["updated_by"] = user

    col.update_one({"name": name}, {"$set": data})
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
):
    col = get_collection("anchors")
    existing = col.find_one({"name": name}, {"_id": 0, "created_by": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Anchor not found")
    if existing.get("created_by") != user and "admins" not in user_groups:
        raise HTTPException(status_code=403, detail="Only the creator or admins can delete this anchor")
    col.delete_one({"name": name})
    response = JSONResponse(content={"status": "deleted", "anchor": name})
    LogEntry.from_request(
        request=request, response=response,
        resource="anchor", resource_id=name,
        action="delete", success=True,
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
    user_groups: list[str] = Depends(get_current_groups),
):
    projection = {
        "_id": 0, "name": 1, "type": 1, "path": 1, "note": 1,
        "groups": 1, "meta": 1, "project": 1, "env": 1,
        "last_updated": 1, "updated_by": 1,
    }
    anchors = query_collection("anchors", filter, projection)
    visibles = [a for a in anchors if _is_visible(a, user_groups)]
    return JSONResponse(content=visibles)


@compat_router.get("/db/pull/{name}")
def compat_pull(
    name: str,
    user_groups: list[str] = Depends(get_current_groups),
):
    col = get_collection("anchors")
    anchor = col.find_one({"name": name}, {"_id": 0})
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")
    if not _is_visible(anchor, user_groups):
        raise HTTPException(status_code=403, detail="Access denied")
    return JSONResponse(content=anchor)
