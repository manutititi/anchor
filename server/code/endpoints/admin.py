from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from auth.middleware import get_current_user, get_current_groups
from auth.service_token import create_service_token, revoke_service_token, list_service_tokens
from auth.local import create_user

router = APIRouter()


@router.get("/needs-setup", tags=["admin"])
def needs_setup():
    """Public endpoint — returns true if no local users exist yet (bootstrap mode)."""
    from db.client import get_collection
    no_users = get_collection("users").count_documents({}) == 0
    return JSONResponse(content={"needs_setup": no_users})


def _require_admin(
    user: str = Depends(get_current_user),
    groups: list[str] = Depends(get_current_groups),
) -> str:
    if "admins" not in groups:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Service token management
# ---------------------------------------------------------------------------

class TokenCreate(BaseModel):
    name: str
    scopes: list[str]
    expires_at: Optional[datetime] = None


@router.post("/tokens", tags=["admin"])
def admin_create_token(
    body: TokenCreate,
    admin: str = Depends(_require_admin),
):
    """Create a new service token (API key). The raw token is shown only once."""
    raw_token = create_service_token(
        name=body.name,
        scopes=body.scopes,
        created_by=admin,
        expires_at=body.expires_at,
    )
    return JSONResponse(
        status_code=201,
        content={
            "token": raw_token,
            "name": body.name,
            "scopes": body.scopes,
            "note": "Save this token securely — it will not be shown again.",
        },
    )


@router.get("/tokens", tags=["admin"])
def admin_list_tokens(admin: str = Depends(_require_admin)):
    """List all service tokens (hashes hidden)."""
    tokens = list_service_tokens()
    return JSONResponse(content=tokens)


@router.delete("/tokens/{token_id}", tags=["admin"])
def admin_revoke_token(token_id: str, admin: str = Depends(_require_admin)):
    """Revoke a service token by ID."""
    revoke_service_token(token_id)
    return JSONResponse(content={"detail": f"Token '{token_id}' revoked."})


# ---------------------------------------------------------------------------
# Local user management
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str
    password: str
    groups: list[str] = []


@router.get("/users", tags=["admin"])
def admin_list_users(admin: str = Depends(_require_admin)):
    """List all local users (password hashes excluded)."""
    from db.client import get_collection
    col = get_collection("users")
    result = []
    for doc in col.find({}, {"_id": 0, "password_hash": 0}):
        result.append({
            "username": doc.get("username", ""),
            "groups": doc.get("groups", []),
            "created_at": doc.get("created_at", ""),
        })
    return JSONResponse(content=result)


class UserUpdate(BaseModel):
    groups: list[str]


@router.patch("/users/{username}", tags=["admin"])
def admin_update_user(username: str, body: UserUpdate, admin: str = Depends(_require_admin)):
    """Update a local user's groups."""
    from db.client import get_collection
    col = get_collection("users")
    result = col.update_one({"username": username}, {"$set": {"groups": body.groups}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    return JSONResponse(content={"detail": f"User '{username}' updated.", "groups": body.groups})


@router.delete("/users/{username}", tags=["admin"])
def admin_delete_user(username: str, admin: str = Depends(_require_admin)):
    """Delete a local user by username."""
    from db.client import get_collection
    col = get_collection("users")
    result = col.delete_one({"username": username})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    return JSONResponse(content={"detail": f"User '{username}' deleted."})


@router.get("/logs", tags=["admin"])
def admin_get_logs(
    admin: str = Depends(_require_admin),
    limit: int = Query(default=50, le=500),
    skip: int = Query(default=0, ge=0),
    user: str = Query(default=""),
    action: str = Query(default=""),
    resource: str = Query(default=""),
    success: str = Query(default=""),   # "true" | "false" | ""
):
    """Paginated audit log. Sorted newest-first."""
    from db.client import get_collection
    col = get_collection("log")
    query: dict = {}
    if user:     query["user"]     = user
    if action:   query["action"]   = action
    if resource: query["resource"] = resource
    if success in ("true", "false"):
        query["success"] = success == "true"

    total = col.count_documents(query)
    docs = list(
        col.find(query, {"_id": 0})
           .sort("timestamp", -1)
           .skip(skip)
           .limit(limit)
    )
    return JSONResponse(content={"total": total, "skip": skip, "limit": limit, "logs": docs})


@router.get("/secrets", tags=["admin"])
def admin_list_secrets(admin: str = Depends(_require_admin)):
    """All secrets metadata — no plaintext, no crypto fields. Admin only."""
    from db.client import get_collection
    col = get_collection("ref")
    result = []
    for doc in col.find({}, {
        "_id": 0, "id": 1, "description": 1, "created_by": 1,
        "groups": 1, "users": 1, "allow_group_edit": 1,
        "version": 1, "created_at": 1, "last_updated": 1, "expires_at": 1,
    }):
        result.append({
            "id":               doc.get("id", ""),
            "description":      doc.get("description", ""),
            "created_by":       doc.get("created_by", ""),
            "groups":           doc.get("groups", []),
            "users":            doc.get("users", []),
            "allow_group_edit": doc.get("allow_group_edit", False),
            "version":          doc.get("version", 1),
            "created_at":       doc.get("created_at", ""),
            "last_updated":     doc.get("last_updated", ""),
            "expires_at":       doc.get("expires_at"),
        })
    return JSONResponse(content=result)


@router.post("/users", tags=["admin"])
def admin_create_user(body: UserCreate, request: Request):
    """Create a local user.

    If no users exist yet (bootstrap), this endpoint is open so the first
    admin can be created without credentials. After that, admin auth is required.
    """
    from db.client import get_collection
    no_users_yet = get_collection("users").count_documents({}) == 0

    if not no_users_yet:
        # Enforce admin auth once the first user exists
        current_user = request.state.user
        current_groups = getattr(request.state, "groups", []) or []
        if not current_user or "admins" not in current_groups:
            raise HTTPException(status_code=403, detail="Admin access required")

    create_user(body.username, body.password, body.groups)
    return JSONResponse(
        status_code=201,
        content={"detail": f"User '{body.username}' created.", "groups": body.groups},
    )
