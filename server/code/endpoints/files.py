from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def list_files():
    return {"status": "ok"}
