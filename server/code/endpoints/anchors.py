from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
from datetime import datetime, timezone
from typing import List
import shutil
import json
import re
import os
from code.auth.session import get_current_user, require_group
from core.utils import matches_filter
from code.core.auth_checker_user_groups import check_anchor_access


router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Sube desde /code/endpoints/ a la raíz
ANCHORS_DIR = BASE_DIR / "anchors"
ANCHORS_DIR.mkdir(parents=True, exist_ok=True)

@router.get("")
def list_anchors(filter: List[str] = Query(default=[])):
    anchors = []
    for file in ANCHORS_DIR.glob("*.json"):
        try:
            with open(file) as f:
                data = json.load(f)

            matched = all(matches_filter(data, f_expr) for f_expr in filter)
            if matched:
                anchors.append(file.stem)

        except Exception:
            continue
    return anchors


@router.get("/{name}")
def get_anchor(name: str):
    file_path = ANCHORS_DIR / f"{name}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Anchor not found")
    return FileResponse(file_path)


@router.post("/_upload")
def upload_anchor(file: UploadFile = File(...)):
    try:
        data = json.load(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    if "type" not in data:
        raise HTTPException(status_code=400, detail="Anchor missing required 'type' field")

    anchor_name = data.get("name") or data.get("id") or file.filename.rsplit(".", 1)[0]
    if not re.match(r"^[a-zA-Z0-9_\-]+$", anchor_name):
        raise HTTPException(status_code=400, detail="Invalid or missing anchor name")

    dst = ANCHORS_DIR / f"{anchor_name}.json"
    try:
        with open(dst, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {e}")

    return {
        "status": "ok",
        "saved_as": str(dst),
        "anchor_name": anchor_name,
        "last_updated": data["last_updated"]
    }


@router.delete("/{name}")
def delete_anchor(name: str):
    path = ANCHORS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        return {"status": "deleted"}
    else:
        raise HTTPException(status_code=404, detail="Anchor not found")



@router.get("/{name}/raw")
def get_anchor_raw(name: str, request: Request, user: str = Depends(get_current_user)):
    file_path = ANCHORS_DIR / f"{name}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Anchor not found")

    try:
        with open(file_path) as f:
            data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON or read error: {e}")

    check_anchor_access(data, request)
    return data
