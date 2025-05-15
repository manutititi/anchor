from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from code.auth.session import get_current_groups, get_current_user
from code.core.ancdb import ancDB
from core.filter import query_collection

router = APIRouter()
db = ancDB()

def is_visible(anchor: dict, user_groups: list[str]) -> bool:
    if "admins" in user_groups:
        return True  
    groups = anchor.get("groups", [])
    return not groups or "all" in groups or any(g in user_groups for g in groups)

# POST /db/upload/<name>
@router.post("/db/upload/{filename}", tags=["db"])
async def upload_anchor_to_db(
    filename: str,
    request: Request,
    user: str = Depends(get_current_user)
):
    data = await request.json()
    result = db.upload_anchor(filename, data, user)
    return JSONResponse(result)

# GET /db/list
@router.get("/db/list", tags=["db"])
def list_anchors_from_db(
    request: Request,
    user_groups: list[str] = Depends(get_current_groups),
    filter: str = ""
):
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

    anchors = query_collection("anchors", filter, projection)
    visibles = [a for a in anchors if is_visible(a, user_groups)]
    return JSONResponse(content=visibles)

# GET /db/pull/<name>
@router.get("/db/pull/{name}", tags=["db"])
def pull_anchor(
    name: str,
    user_groups: list[str] = Depends(get_current_groups)
):
    collection = db.get_collection("anchors")
    anchor = collection.find_one({"name": name}, {"_id": 0})

    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")

    if not is_visible(anchor, user_groups):
        raise HTTPException(status_code=403, detail="Access denied")

    return JSONResponse(content=anchor)





