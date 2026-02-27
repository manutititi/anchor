from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from auth.middleware import get_current_user, get_current_groups, get_current_scopes
from vault.crypto import encrypt, decrypt
from vault import access, versions
from db.client import get_collection
from core.utils import now_tz
from core.logger import LogEntry

router = APIRouter()


# ---------------------------------------------------------------------------
# List secrets
# ---------------------------------------------------------------------------

@router.get("", tags=["vault"])
def list_secrets(
    request: Request,
    prefix: str = Query(default=""),
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    col = get_collection("ref")
    query: dict = {}
    if prefix:
        query["id"] = {"$regex": f"^{prefix}"}

    docs = col.find(query, {
        "_id": 0, "id": 1, "description": 1, "version": 1,
        "created_by": 1, "created_at": 1, "last_updated": 1,
        "expires_at": 1, "groups": 1, "users": 1, "allow_group_edit": 1,
    })

    result = []
    for doc in docs:
        if access.is_visible(doc, current_user, current_groups, current_scopes):
            result.append({
                "id": doc["id"],
                "description": doc.get("description", ""),
                "version": doc.get("version", 1),
                "created_by": doc.get("created_by", ""),
                "created_at": doc.get("created_at", ""),
                "last_updated": doc.get("last_updated", ""),
                "expires_at": doc.get("expires_at"),
                "owned": doc.get("created_by") == current_user,
                "groups": doc.get("groups", []),
                "users": doc.get("users", []),
                "allow_group_edit": doc.get("allow_group_edit", False),
            })
    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# Create secret
# ---------------------------------------------------------------------------

@router.post("/{path:path}", status_code=201, tags=["vault"])
async def create_secret(
    path: str,
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
):
    data = await request.json()
    col = get_collection("ref")

    if col.find_one({"id": path}):
        raise HTTPException(
            status_code=409,
            detail=f"Secret '{path}' already exists. Use PUT to update.",
        )

    encrypted = encrypt(data.get("plaintext", ""), path)
    # transfer_to lets the creator immediately assign ownership to someone else on creation
    owner = data.get("transfer_to") or current_user
    doc = {
        "type": "secret",
        "id": path,
        "description": data.get("description", ""),
        "encoding": encrypted["encoding"],
        "value": encrypted["value"],
        "iv": encrypted["iv"],
        "tag": encrypted["tag"],
        "version": 1,
        "created_at": now_tz(),
        "last_updated": now_tz(),
        "created_by": owner,
        "updated_by": current_user,
        "users": data.get("users", []),
        "groups": data.get("groups", []),
        "allow_group_edit": data.get("allow_group_edit", False),
        "expires_at": data.get("expires_at"),
        "metadata": data.get("metadata", {}),
    }
    col.insert_one(doc)
    versions.save_version(path, encrypted, 1, current_user)

    response = JSONResponse(
        status_code=201,
        content={"detail": f"Secret '{path}' created.", "id": path},
    )
    LogEntry.from_request(
        request=request, response=response,
        resource="secret", resource_id=path,
        action="create", success=True,
    ).save_default()
    return response


# ---------------------------------------------------------------------------
# Get secret  (also handles /{path}/versions sub-path)
# ---------------------------------------------------------------------------

@router.get("/{path:path}", tags=["vault"])
async def get_secret(
    path: str,
    request: Request,
    version: int | None = Query(default=None),
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    # Sub-path: GET /vault/{secret_id}/versions
    if path.endswith("/versions"):
        secret_id = path[: -len("/versions")]
        col = get_collection("ref")
        secret = col.find_one({"id": secret_id})
        if not secret:
            raise HTTPException(status_code=404, detail="Secret not found")
        if not access.can_read_plaintext(secret, current_user, current_groups, current_scopes):
            raise HTTPException(status_code=403, detail="Access denied")
        return JSONResponse(content=versions.list_versions(secret_id))

    col = get_collection("ref")
    secret = col.find_one({"id": path})

    if not secret:
        response = JSONResponse(status_code=404, content={"detail": "Secret not found"})
        LogEntry.from_request(
            request=request, response=response,
            resource="secret", resource_id=path,
            action="get", success=False, extra={"reason": "not_found"},
        ).save_default()
        return response

    if not access.can_read_plaintext(secret, current_user, current_groups, current_scopes):
        response = JSONResponse(status_code=403, content={"detail": "Access denied"})
        LogEntry.from_request(
            request=request, response=response,
            resource="secret", resource_id=path,
            action="get", success=False, extra={"reason": "access_denied"},
        ).save_default()
        return response

    if version is not None:
        ver_doc = versions.get_version(path, version)
        if not ver_doc:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")
        encrypted = {"value": ver_doc["value"], "iv": ver_doc["iv"], "tag": ver_doc["tag"]}
    else:
        encrypted = {"value": secret["value"], "iv": secret["iv"], "tag": secret["tag"]}

    try:
        plaintext = decrypt(encrypted, path)
    except Exception as e:
        response = JSONResponse(status_code=500, content={"detail": f"Decryption failed: {e}"})
        LogEntry.from_request(
            request=request, response=response,
            resource="secret", resource_id=path,
            action="get", success=False, extra={"reason": "decryption_failed"},
        ).save_default()
        return response

    response = JSONResponse(content={
        "id": path,
        "plaintext": plaintext,
        "description": secret.get("description", ""),
        "version": version if version is not None else secret.get("version", 1),
    })
    LogEntry.from_request(
        request=request, response=response,
        resource="secret", resource_id=path,
        action="get", success=True,
    ).save_default()
    return response


# ---------------------------------------------------------------------------
# Update secret
# ---------------------------------------------------------------------------

@router.put("/{path:path}", tags=["vault"])
async def update_secret(
    path: str,
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    col = get_collection("ref")
    secret = col.find_one({"id": path})

    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")

    if not access.can_edit(secret, current_user, current_groups, current_scopes):
        raise HTTPException(status_code=403, detail="Access denied: insufficient permissions")

    data = await request.json()
    update_fields: dict = {}
    is_creator = secret.get("created_by") == current_user

    # Value fields — any editor can change
    if "plaintext" in data:
        new_version = secret.get("version", 1) + 1
        encrypted = encrypt(data["plaintext"], path)
        update_fields.update(encrypted)
        update_fields["version"] = new_version
        versions.save_version(path, encrypted, new_version, current_user)

    if "description" in data:
        update_fields["description"] = data["description"]
    if "metadata" in data:
        update_fields["metadata"] = data["metadata"]

    # ACL fields — creator only (service tokens with admin scope are also allowed)
    acl_fields = {"groups", "users", "allow_group_edit", "transfer_to"}
    if acl_fields & data.keys():
        if not is_creator and "admin" not in current_scopes:
            raise HTTPException(
                status_code=403,
                detail="Only the creator can change who has access to this secret",
            )
        if "groups" in data:
            update_fields["groups"] = data["groups"]
        if "users" in data:
            update_fields["users"] = data["users"]
        if "allow_group_edit" in data:
            update_fields["allow_group_edit"] = bool(data["allow_group_edit"])
        if "transfer_to" in data:
            update_fields["created_by"] = data["transfer_to"]

    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    update_fields["last_updated"] = now_tz()
    update_fields["updated_by"] = current_user
    col.update_one({"id": path}, {"$set": update_fields})

    response = JSONResponse(content={
        "detail": f"Secret '{path}' updated.",
        "version": update_fields.get("version", secret.get("version", 1)),
    })
    extra: dict = {"fields_changed": list(update_fields.keys())}
    if "created_by" in update_fields:
        extra["transferred_to"] = update_fields["created_by"]
    LogEntry.from_request(
        request=request, response=response,
        resource="secret", resource_id=path,
        action="update", success=True,
        extra=extra,
    ).save_default()
    return response


# ---------------------------------------------------------------------------
# Delete secret
# ---------------------------------------------------------------------------

@router.delete("/{path:path}", tags=["vault"])
async def delete_secret(
    path: str,
    request: Request,
    current_user: str = Depends(get_current_user),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    col = get_collection("ref")
    secret = col.find_one({"id": path})

    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")

    if not access.can_delete(secret, current_user, current_scopes):
        raise HTTPException(status_code=403, detail="Only the creator can delete this secret")

    col.delete_one({"id": path})

    response = JSONResponse(content={"detail": f"Secret '{path}' deleted."})
    LogEntry.from_request(
        request=request, response=response,
        resource="secret", resource_id=path,
        action="delete", success=True,
    ).save_default()
    return response


# ---------------------------------------------------------------------------
# Backward-compatible /ref/... aliases (deprecated)
# ---------------------------------------------------------------------------

compat_router = APIRouter(tags=["ref (deprecated)"])


@compat_router.get("/ref/list")
def compat_list_secrets(
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    col = get_collection("ref")
    docs = col.find({}, {"_id": 0, "id": 1, "description": 1, "groups": 1, "users": 1, "created_by": 1})
    result = []
    for doc in docs:
        if access.is_visible(doc, current_user, current_groups, current_scopes):
            result.append({
                "id": doc["id"],
                "description": doc.get("description", ""),
                "owned": doc.get("created_by") == current_user,
            })
    return JSONResponse(content=result)


@compat_router.get("/ref/get/{ref_id}")
def compat_get_secret(
    ref_id: str,
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    col = get_collection("ref")
    secret = col.find_one({"id": ref_id})
    if not secret:
        return JSONResponse(status_code=404, content={"detail": "Ref not found"})
    if not access.can_read_plaintext(secret, current_user, current_groups, current_scopes):
        return JSONResponse(status_code=403, content={"detail": "Access denied"})
    try:
        plaintext = decrypt(
            {"value": secret["value"], "iv": secret["iv"], "tag": secret["tag"]},
            ref_id,
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Decryption failed: {e}"})
    return JSONResponse(content={"id": ref_id, "plaintext": plaintext, "description": secret.get("description", "")})


@compat_router.post("/ref/set")
async def compat_set_secret(
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
):
    data = await request.json()
    ref_id = data.get("id")
    if not ref_id:
        raise HTTPException(status_code=400, detail="Missing field: id")

    col = get_collection("ref")
    if col.find_one({"id": ref_id}):
        raise HTTPException(status_code=409, detail="A ref with this ID already exists.")

    encrypted = encrypt(data.get("plaintext", ""), ref_id)
    doc = {
        "type": "secret",
        "id": ref_id,
        "description": data.get("description", ""),
        "encoding": encrypted["encoding"],
        "value": encrypted["value"],
        "iv": encrypted["iv"],
        "tag": encrypted["tag"],
        "version": 1,
        "created_at": now_tz(),
        "last_updated": now_tz(),
        "created_by": current_user,
        "updated_by": current_user,
        "users": data.get("users", []),
        "groups": data.get("groups", current_groups),
        "allow_group_edit": data.get("allow_group_edit", True),
    }
    col.insert_one(doc)
    versions.save_version(ref_id, encrypted, 1, current_user)
    return JSONResponse(
        status_code=201,
        content={"detail": f"Secret '{ref_id}' stored successfully.", "id": ref_id},
    )


@compat_router.delete("/ref/{ref_id}")
async def compat_delete_secret(
    ref_id: str,
    request: Request,
    current_user: str = Depends(get_current_user),
    current_scopes: list[str] = Depends(get_current_scopes),
):
    col = get_collection("ref")
    secret = col.find_one({"id": ref_id})
    if not secret:
        return JSONResponse(status_code=404, content={"detail": "Ref not found"})
    if not access.can_delete(secret, current_user, current_scopes):
        return JSONResponse(status_code=403, content={"detail": "Only the creator can delete this secret"})
    col.delete_one({"id": ref_id})
    return JSONResponse(content={"detail": f"Secret '{ref_id}' deleted successfully."})
