from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import RootModel
from typing import Any
from code.core.db_collection import get_mongo_collection
from code.auth.session import get_current_groups, get_current_user
from collections import OrderedDict
from code.core.utils import now_tz
import json
import os






router = APIRouter()

@router.post("/db/upload/{filename}", tags=["db"])
async def upload_anchor_to_db(
    filename: str,
    request: Request,
    user: str = Depends(get_current_user)  # token needed
):
    data = await request.json()

    # Create name if not define
    if "name" not in data or not data["name"]:
        name = os.path.splitext(filename)[0]
        data["name"] = name
    else:
        name = data["name"]

    collection = get_mongo_collection("anchors")
    existing = collection.find_one({"name": name})

    now = now_tz()

    # if new
    if not existing:
        data["created_at"] = now
        data["created_by"] = user

    # Salways update
    data["last_updated"] = now
    data["updated_by"] = user

    # Reorder
    reordered = {
        k: data[k]
        for k in ["type", "name", "groups"]
        if k in data
    }
    reordered.update({k: v for k, v in data.items() if k not in reordered})

    result = collection.replace_one({"name": name}, reordered, upsert=True)

    return JSONResponse({
        "status": "ok",
        "anchor": name,
        "inserted": result.upserted_id is not None,
        "user": user
    })






### list ancs depends on ldap groups
@router.get("/db/list", tags=["db"])
def list_anchors_from_db(
    request: Request,
    user_groups: list[str] = Depends(get_current_groups)
):
    collection = get_mongo_collection("anchors")

    projection = {
        "_id": 0,
        "name": 1,
        "type": 1,
        "path": 1,
        "note": 1,
        "groups": 1,
        "meta": 1,
        "project": 1,
        "env": 1,
        "last_updated": 1,
        "updated_by": 1
    }

    all_anchors = list(collection.find({}, projection))

    visible = []
    for anchor in all_anchors:
        anchor_groups = anchor.get("groups", [])
        if not anchor_groups or "all" in anchor_groups:
            visible.append(anchor)
        elif any(group in user_groups for group in anchor_groups):
            visible.append(anchor)

    return JSONResponse(content=visible)

