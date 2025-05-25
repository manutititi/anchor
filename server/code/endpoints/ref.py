from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from code.core.ancdb import ancDB
from code.core.utils import now_tz
from auth.session import get_current_user, get_current_groups

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

    return JSONResponse(status_code=201, content={
        "detail": f"Secret '{ref_id}' stored successfully.",
        "id": ref_id
    })




def is_ref_visible(ref: dict, user: str, groups: list[str]) -> bool:
    """
    Si hay usuarios definidos, el usuario debe estar listado.
    Si no hay usuarios, se permite acceso si pertenece a algún grupo válido.
    """
    if "users" in ref and ref["users"]:
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
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
):
    db = ancDB()
    collection = db.get_collection("ref")
    ref = collection.find_one({"id": ref_id})

    if not ref:
        raise HTTPException(status_code=404, detail="Ref not found")

    if not is_ref_visible(ref, current_user, current_groups):
        if "users" in ref and ref["users"]:
            raise HTTPException(status_code=403, detail="Access denied: restricted to specific user(s)")
        raise HTTPException(status_code=403, detail="Access denied: insufficient group permissions")

    try:
        plaintext = decrypt_secret(ref["value"], ref["iv"], ref["tag"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {e}")

    return JSONResponse(status_code=200, content={
        "id": ref_id,
        "plaintext": plaintext,
        "description": ref.get("description", "")
    })


@router.get("/list", tags=["ref"])
async def list_visible_refs(
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
):
    db = ancDB()
    collection = db.get_collection("ref")

    docs = collection.find({}, {"_id": 0, "id": 1, "description": 1, "groups": 1, "users": 1})
    visibles = []

    for ref in docs:
        if is_ref_visible(ref, current_user, current_groups):
            visibles.append({
                "id": ref["id"],
                "description": ref.get("description", "")
            })

    return JSONResponse(status_code=200, content=visibles)


@router.get("/pull/{ref_id}", tags=["ref"])
async def pull_ref_json(
    ref_id: str,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups),
):
    db = ancDB()
    collection = db.get_collection("ref")
    ref = collection.find_one({"id": ref_id}, {"_id": 0})

    if not ref:
        raise HTTPException(status_code=404, detail="Ref not found")

    if not is_ref_visible(ref, current_user, current_groups):
        raise HTTPException(status_code=403, detail="Access denied")

    return JSONResponse(content=ref)




@router.post("/update", tags=["ref"])
async def update_ref(
    request: Request,
    current_user: str = Depends(get_current_user),
    current_groups: list[str] = Depends(get_current_groups)
):
    data = await request.json()
    ref_id = data.get("id")
    if not ref_id:
        raise HTTPException(status_code=400, detail="Missing field: id")

    db = ancDB()
    collection = db.get_collection("ref")
    ref = collection.find_one({"id": ref_id})

    if not ref:
        raise HTTPException(status_code=404, detail="Ref not found")

    is_creator = ref.get("created_by") == current_user
    allow_group_edit = ref.get("allow_group_edit", True)
    has_group_access = any(group in ref.get("groups", []) for group in current_groups)
    is_user_allowed = current_user in ref.get("users", [])

    # Permissions
    if ref.get("users"):
        if not is_user_allowed:
            raise HTTPException(status_code=403, detail="Access denied: only allowed user(s) can edit")
    elif not is_creator and not allow_group_edit:
        raise HTTPException(status_code=403, detail="Access denied: only creator can edit this secret")
    elif not is_creator and not has_group_access:
        raise HTTPException(status_code=403, detail="Access denied: insufficient group permissions")

    # allowed fields
    allowed_fields = {"description", "groups", "users", "meta"}
    update_fields = {k: v for k, v in data.items() if k in allowed_fields}

    # chiper if needed
    if "plaintext" in data:
        encrypted = encrypt_secret(data["plaintext"])
        update_fields.update(encrypted)

    # Modify allow_group_edit
    if "allow_group_edit" in data:
        if not is_creator:
            raise HTTPException(status_code=403, detail="Only the creator can modify allow_group_edit")
        update_fields["allow_group_edit"] = bool(data["allow_group_edit"])

    # Never save plaintext
    update_fields.pop("plaintext", None)

    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields provided for update")

    update_fields["last_updated"] = now_tz()
    update_fields["updated_by"] = current_user

    collection.update_one({"id": ref_id}, {"$set": update_fields})

    return JSONResponse(content={
        "detail": f"Secret '{ref_id}' updated successfully.",
        "updated": list(update_fields.keys())
    })
