from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from auth.ldap import ldap_authenticate, get_user_groups
from auth.session import create_token

router = APIRouter()

class LoginData(BaseModel):
    username: str
    password: str

@router.post("/auth/login")
def login(data: LoginData):
    if not ldap_authenticate(data.username, data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    groups = get_user_groups(data.username)
    token = create_token(data.username, groups)

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": data.username,
        "groups": groups,
    }
