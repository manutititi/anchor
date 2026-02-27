from ldap3 import Server, Connection, ALL, SUBTREE
from fastapi import HTTPException
from config import settings
import logging

logger = logging.getLogger(__name__)


def _check_enabled():
    if not settings.ldap_enabled:
        raise HTTPException(status_code=400, detail="LDAP authentication is not enabled")


def get_user_dn(username: str) -> str | None:
    _check_enabled()
    server = Server(settings.LDAP_SERVER, get_info=ALL)
    conn = Connection(
        server,
        user=settings.LDAP_ADMIN_DN,
        password=settings.LDAP_ADMIN_PASSWORD,
        auto_bind=True,
    )
    conn.search(
        search_base=f"ou=users,{settings.LDAP_BASE_DN}",
        search_filter=f"(uid={username})",
        search_scope=SUBTREE,
        attributes=["uid"],
    )
    if conn.entries:
        return conn.entries[0].entry_dn
    return None


def ldap_authenticate(username: str, password: str) -> bool:
    _check_enabled()
    user_dn = get_user_dn(username)
    if not user_dn:
        logger.warning("LDAP user not found: %s", username)
        return False
    try:
        server = Server(settings.LDAP_SERVER, get_info=ALL)
        Connection(server, user=user_dn, password=password, auto_bind=True)
        return True
    except Exception as e:
        logger.warning("LDAP authentication failed for %s: %s", username, e)
        return False


def get_user_groups(username: str) -> list[str]:
    _check_enabled()
    user_dn = get_user_dn(username)
    if not user_dn:
        return []
    server = Server(settings.LDAP_SERVER, get_info=ALL)
    conn = Connection(
        server,
        user=settings.LDAP_ADMIN_DN,
        password=settings.LDAP_ADMIN_PASSWORD,
        auto_bind=True,
    )
    conn.search(
        search_base=f"ou=groups,{settings.LDAP_BASE_DN}",
        search_filter=f"(member={user_dn})",
        search_scope=SUBTREE,
        attributes=["cn"],
    )
    return [entry.cn.value for entry in conn.entries]
