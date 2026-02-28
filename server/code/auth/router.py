import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from auth.token import create_token
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginData(BaseModel):
    username: str
    password: str


def _sync_ldap_user(username: str, groups: list[str]) -> None:
    """
    Upsert a minimal user profile in MongoDB after successful LDAP login.
    This is NOT used for authentication — only for audit/admin visibility.
    Passwords are never stored here.
    """
    try:
        from db.client import get_collection
        from integrations.ldap.provider import LDAPProvider
        from core.utils import now_tz

        attrs = LDAPProvider().get_user_attributes(username)
        col = get_collection("users")
        col.update_one(
            {"username": username},
            {"$set": {
                "username": username,
                "source": "ldap",
                "groups": groups,
                "last_login": now_tz(),
                "last_ldap_sync": now_tz(),
                "display_name": attrs.get("displayName") or attrs.get("cn") or username,
                "email": attrs.get("mail"),
            }},
            upsert=True,
        )
    except Exception as exc:
        # Sync failure must not block the login
        logger.warning("LDAP user sync failed for %s: %s", username, exc)


@router.post("/auth/login", tags=["auth"])
def login(data: LoginData):
    """Login with local or LDAP credentials. Returns a JWT Bearer token."""
    authenticated = False
    groups: list[str] = []
    source: str = "local"

    if settings.LOCAL_AUTH_ENABLED:
        from auth.local import authenticate_local, get_user_groups as local_groups
        if authenticate_local(data.username, data.password):
            authenticated = True
            groups = local_groups(data.username)
            source = "local"

    if not authenticated:
        from integrations.ldap.provider import LDAPProvider
        if LDAPProvider().is_enabled():
            from auth.ldap import ldap_authenticate, get_user_groups as ldap_groups
            if ldap_authenticate(data.username, data.password):
                authenticated = True
                groups = ldap_groups(data.username)
                source = "ldap"

    if not authenticated:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if source == "ldap":
        _sync_ldap_user(data.username, groups)

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
    from integrations.ldap.provider import LDAPProvider
    if not LDAPProvider().is_enabled():
        raise HTTPException(status_code=400, detail="LDAP authentication is not enabled")
    from auth.ldap import ldap_authenticate, get_user_groups as ldap_groups
    if not ldap_authenticate(data.username, data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    groups = ldap_groups(data.username)
    _sync_ldap_user(data.username, groups)
    token = create_token(data.username, groups)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": data.username,
        "groups": groups,
    }
