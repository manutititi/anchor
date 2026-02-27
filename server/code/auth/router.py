from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from auth.token import create_token
from config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class LoginData(BaseModel):
    username: str
    password: str


@router.post("/auth/login", tags=["auth"])
def login(data: LoginData):
    """Login with local or LDAP credentials. Returns a JWT Bearer token."""
    authenticated = False
    groups: list[str] = []

    if settings.LOCAL_AUTH_ENABLED:
        from auth.local import authenticate_local, get_user_groups as local_groups
        if authenticate_local(data.username, data.password):
            authenticated = True
            groups = local_groups(data.username)

    if not authenticated and settings.ldap_enabled:
        from auth.ldap import ldap_authenticate, get_user_groups as ldap_groups
        if ldap_authenticate(data.username, data.password):
            authenticated = True
            groups = ldap_groups(data.username)

    if not authenticated:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(data.username, groups)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": data.username,
        "groups": groups,
    }


@router.post("/auth/login/local", tags=["auth"])
def login_local(data: LoginData):
    """Force login via local user store (MongoDB users collection)."""
    if not settings.LOCAL_AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="Local authentication is not enabled")
    from auth.local import authenticate_local, get_user_groups as local_groups
    if not authenticate_local(data.username, data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    groups = local_groups(data.username)
    token = create_token(data.username, groups)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": data.username,
        "groups": groups,
    }


@router.post("/auth/login/ldap", tags=["auth"])
def login_ldap(data: LoginData):
    """Force login via LDAP."""
    if not settings.ldap_enabled:
        raise HTTPException(status_code=400, detail="LDAP authentication is not enabled")
    from auth.ldap import ldap_authenticate, get_user_groups as ldap_groups
    if not ldap_authenticate(data.username, data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    groups = ldap_groups(data.username)
    token = create_token(data.username, groups)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": data.username,
        "groups": groups,
    }
