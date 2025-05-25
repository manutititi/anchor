from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from code.core.ancdb import ancDB
from code.core.utils import now_tz
from auth.session import get_current_user, get_current_groups
from core.logger import LogEntry

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import base64
import os

router = APIRouter()

# Clave de cifrado (32 bytes base64)
ENC_KEY = base64.b64decode(os.getenv(
    "SECRET_ENCRYPTION_KEY",
    "HhYXbo7Nbp3fKU7xvku0tkgZ524k40AFY3NjzK+szoU="  # valor de prueba, reemplazar en prod
))

def encrypt_secret(plaintext: str) -> dict:
    iv = get_random_bytes(12)
    cipher = AES.new(ENC_KEY, AES.MODE_GCM, nonce=iv)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())

    return {
        "value": base64.b64encode(ciphertext).decode(),
        "iv": base64.b64encode(iv).decode(),
        "tag": base64.b64encode(tag).decode(),
        "encoding": "aes256-gcm"
    }



@router.post("/set", tags=["ref"])
async def set_secret_ref(
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
):
    data = await request.json()
    required = ["id", "plaintext", "description"]

    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")

    ref_id = data["id"]
    db = ancDB()
    collection = db.get_collection("ref")

    if collection.find_one({"id": ref_id}):
        raise HTTPException(status_code=409, detail="A ref with this ID already exists.")

    encrypted = encrypt_secret(data["plaintext"])

    ref_doc = {
        "type": "secret",
        "id": ref_id,
        "description": data["description"],
        "encoding": encrypted["encoding"],
        "value": encrypted["value"],
        "iv": encrypted["iv"],
        "tag": encrypted["tag"],
        "created_at": now_tz(),
        "last_updated": now_tz(),
        "created_by": current_user,
        "updated_by": current_user,
        "users": data.get("users", []),
        "groups": data.get("groups", current_groups),
        "allow_group_edit": data.get("allow_group_edit", True)
    }

    collection.insert_one(ref_doc)

    response = JSONResponse(status_code=201, content={
        "detail": f"Secret '{ref_id}' stored successfully.",
        "id": ref_id
    })

    # Log 
    LogEntry.from_request(
        request=request,
        response=response,
        resource="secret",
        resource_id=ref_id,
        action="push",
        success=True,
        extra={
            "description": data["description"],
            "groups": ref_doc["groups"],
            "has_group_edit": ref_doc["allow_group_edit"]
        }
    ).save_default()

    return response






def is_ref_visible(ref: dict, user: str, groups: list[str]) -> bool:
    """
    Determine if an user can access a secret
    - creator always has access
    - Users override group permissions
    - If not users, next applies groups. 
    - If not users and not groups creator 
    """
    if user == ref.get("created_by"):
        return True  # creator always has access 

    if ref.get("users"):
        return user in ref["users"]

    return any(group in ref.get("groups", []) for group in groups)


def decrypt_secret(value_b64: str, iv_b64: str, tag_b64: str) -> str:
    cipher = AES.new(ENC_KEY, AES.MODE_GCM, nonce=base64.b64decode(iv_b64))
    return cipher.decrypt_and_verify(
        base64.b64decode(value_b64),
        base64.b64decode(tag_b64)
    ).decode()





@router.get("/get/{ref_id}", tags=["ref"])
async def get_secret_ref(
    ref_id: str,
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
):
    db = ancDB()
    collection = db.get_collection("ref")
    ref = collection.find_one({"id": ref_id})

    if not ref:
        response = JSONResponse(status_code=404, content={"detail": "Ref not found"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id=ref_id,
            action="get",
            success=False,
            extra={"reason": "not_found"}
        ).save_default()
        return response

    if not is_ref_visible(ref, current_user, current_groups):
        reason = "user_restricted" if ref.get("users") else "group_restricted"
        response = JSONResponse(status_code=403, content={"detail": "Access denied"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id=ref_id,
            action="get",
            success=False,
            extra={
                "reason": reason
            }
        ).save_default()
        return response

    try:
        plaintext = decrypt_secret(ref["value"], ref["iv"], ref["tag"])
    except Exception as e:
        response = JSONResponse(status_code=500, content={"detail": f"Decryption failed: {e}"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id=ref_id,
            action="get",
            success=False,
            extra={"reason": "decryption_failed"}
        ).save_default()
        return response

    response = JSONResponse(status_code=200, content={
        "id": ref_id,
        "plaintext": plaintext,
        "description": ref.get("description", "")
    })

    LogEntry.from_request(
        request=request,
        response=response,
        resource="secret",
        resource_id=ref_id,
        action="get",
        success=True
    ).save_default()

    return response


@router.get("/list", tags=["ref"])
async def list_visible_refs(
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
):
    db = ancDB()
    collection = db.get_collection("ref")

    # ruquested
    docs = collection.find({}, {
        "_id": 0,
        "id": 1,
        "description": 1,
        "groups": 1,
        "users": 1,
        "created_by": 1
    })

    visibles = []
    for ref in docs:
        if is_ref_visible(ref, current_user, current_groups):
            visibles.append({
                "id": ref["id"],
                "description": ref.get("description", ""),
                "owned": ref.get("created_by") == current_user
            })

    return JSONResponse(status_code=200, content=visibles)



@router.get("/pull/{ref_id}", tags=["ref"])
async def pull_ref_json(
    ref_id: str,
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
):
    db = ancDB()
    collection = db.get_collection("ref")
    ref = collection.find_one({"id": ref_id}, {"_id": 0})

    if not ref:
        response = JSONResponse(status_code=404, content={"detail": "Ref not found"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id=ref_id,
            action="pull",
            success=False,
            extra={"reason": "not_found"}
        ).save_default()
        return response

    if not is_ref_visible(ref, current_user, current_groups):
        response = JSONResponse(status_code=403, content={"detail": "Access denied"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id=ref_id,
            action="pull",
            success=False,
            extra={
                "reason": "access_denied"
            }
        ).save_default()
        return response

    response = JSONResponse(content=ref)

    LogEntry.from_request(
        request=request,
        response=response,
        resource="secret",
        resource_id=ref_id,
        action="pull",
        success=True,
        extra={
            "description": ref.get("description", ""),
            "groups": ref.get("groups", []),
            "users": ref.get("users", [])
        }
    ).save_default()

    return response




@router.post("/update", tags=["ref"])
async def update_ref(
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups)
):
    data = await request.json()
    ref_id = data.get("id")

    if not ref_id:
        response = JSONResponse(status_code=400, content={"detail": "Missing field: id"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id="undefined",
            action="update",
            success=False,
            extra={"reason": "missing_id"}
        ).save_default()
        return response

    db = ancDB()
    collection = db.get_collection("ref")
    ref = collection.find_one({"id": ref_id})

    if not ref:
        response = JSONResponse(status_code=404, content={"detail": "Ref not found"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id=ref_id,
            action="update",
            success=False,
            extra={"reason": "not_found"}
        ).save_default()
        return response

    is_creator = ref.get("created_by") == current_user
    allow_group_edit = ref.get("allow_group_edit", True)
    has_group_access = any(group in ref.get("groups", []) for group in current_groups)
    is_user_allowed = current_user in ref.get("users", [])

    # Permisos
    if not is_creator:
        if ref.get("users") and not is_user_allowed:
            response = JSONResponse(status_code=403, content={"detail": "Access denied: only allowed user(s) can edit"})
            LogEntry.from_request(
                request=request,
                response=response,
                resource="secret",
                resource_id=ref_id,
                action="update",
                success=False,
                extra={"reason": "user_restricted"}
            ).save_default()
            return response

        if not ref.get("users") and not allow_group_edit:
            response = JSONResponse(status_code=403, content={"detail": "Access denied: only creator can edit this secret"})
            LogEntry.from_request(
                request=request,
                response=response,
                resource="secret",
                resource_id=ref_id,
                action="update",
                success=False,
                extra={"reason": "group_edit_forbidden"}
            ).save_default()
            return response

        if not ref.get("users") and not has_group_access:
            response = JSONResponse(status_code=403, content={"detail": "Access denied: insufficient group permissions"})
            LogEntry.from_request(
                request=request,
                response=response,
                resource="secret",
                resource_id=ref_id,
                action="update",
                success=False,
                extra={"reason": "group_restricted"}
            ).save_default()
            return response

    # Campos permitidos
    allowed_fields = {"description", "groups", "users", "meta"}
    update_fields = {k: v for k, v in data.items() if k in allowed_fields}

    if "created_by" in data:
        if not is_creator:
            response = JSONResponse(status_code=403, content={"detail": "Only the original creator can change the owner"})
            LogEntry.from_request(
                request=request,
                response=response,
                resource="secret",
                resource_id=ref_id,
                action="update",
                success=False,
                extra={"reason": "owner_change_forbidden"}
            ).save_default()
            return response
        update_fields["created_by"] = data["created_by"]

    if "plaintext" in data:
        encrypted = encrypt_secret(data["plaintext"])
        update_fields.update(encrypted)

    if "allow_group_edit" in data:
        if not is_creator:
            response = JSONResponse(status_code=403, content={"detail": "Only the creator can modify allow_group_edit"})
            LogEntry.from_request(
                request=request,
                response=response,
                resource="secret",
                resource_id=ref_id,
                action="update",
                success=False,
                extra={"reason": "group_edit_change_forbidden"}
            ).save_default()
            return response
        update_fields["allow_group_edit"] = bool(data["allow_group_edit"])

    update_fields.pop("plaintext", None)

    if not update_fields:
        response = JSONResponse(status_code=400, content={"detail": "No valid fields provided for update"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id=ref_id,
            action="update",
            success=False,
            extra={"reason": "no_valid_fields"}
        ).save_default()
        return response

    update_fields["last_updated"] = now_tz()
    update_fields["updated_by"] = current_user

    # Guardamos cambios
    collection.update_one({"id": ref_id}, {"$set": update_fields})

    response = JSONResponse(content={
        "detail": f"Secret '{ref_id}' updated successfully.",
        "updated": list(update_fields.keys())
    })

    LogEntry.from_request(
        request=request,
        response=response,
        resource="secret",
        resource_id=ref_id,
        action="update",
        success=True,
        extra={
            "fields_changed": list(update_fields.keys()),
            "updated_by": current_user
        }
    ).save_default()

    return response



@router.delete("/delete/{ref_id}", tags=["ref"])
async def delete_ref(
    ref_id: str,
    request: Request,
    current_user: str = Depends(get_current_user),
):
    db = ancDB()
    collection = db.get_collection("ref")
    ref = collection.find_one({"id": ref_id})

    if not ref:
        response = JSONResponse(status_code=404, content={"detail": "Ref not found"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id=ref_id,
            action="del",
            success=False,
            extra={"reason": "not_found"}
        ).save_default()
        return response

    if ref.get("created_by") != current_user:
        response = JSONResponse(status_code=403, content={"detail": "Only the creator can delete this secret"})
        LogEntry.from_request(
            request=request,
            response=response,
            resource="secret",
            resource_id=ref_id,
            action="del",
            success=False,
            extra={
                "reason": "not_creator",
                "created_by": ref.get("created_by")
            }
        ).save_default()
        return response

    collection.delete_one({"id": ref_id})

    response = JSONResponse(status_code=200, content={
        "detail": f"Secret '{ref_id}' deleted successfully."
    })

    LogEntry.from_request(
        request=request,
        response=response,
        resource="secret",
        resource_id=ref_id,
        action="del",
        success=True,
        extra={
            "description": ref.get("description", ""),
            "groups": ref.get("groups", []),
            "deleted_by": current_user
        }
    ).save_default()

    return response


