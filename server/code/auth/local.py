from passlib.context import CryptContext
from fastapi import HTTPException
from db.client import get_collection
from core.utils import now_tz

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_user(username: str, password: str, groups: list[str] = []):
    col = get_collection("users")
    if col.find_one({"username": username}):
        raise HTTPException(status_code=409, detail=f"User '{username}' already exists")
    col.insert_one({
        "username": username,
        "password_hash": pwd_context.hash(password),
        "groups": groups,
        "created_at": now_tz(),
    })


def authenticate_local(username: str, password: str) -> bool:
    col = get_collection("users")
    user = col.find_one({"username": username})
    if not user:
        return False
    return pwd_context.verify(password, user["password_hash"])


def get_user_groups(username: str) -> list[str]:
    col = get_collection("users")
    user = col.find_one({"username": username})
    if not user:
        return []
    return user.get("groups", [])
