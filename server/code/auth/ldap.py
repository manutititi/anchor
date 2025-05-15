from ldap3 import Server, Connection, ALL, SUBTREE
import os

LDAP_SERVER = os.getenv("LDAP_SERVER", "ldap://ldap:389")
BASE_DN = os.getenv("LDAP_BASE_DN", "dc=anchor,dc=local")
ADMIN_DN = os.getenv("LDAP_ADMIN_DN", f"cn=admin,{BASE_DN}")
ADMIN_PASSWORD = os.getenv("LDAP_ADMIN_PASSWORD", "admin")


def get_user_dn(username: str) -> str | None:
    server = Server(LDAP_SERVER, get_info=ALL)
    conn = Connection(server, user=ADMIN_DN, password=ADMIN_PASSWORD, auto_bind=True)

    conn.search(
        search_base=f"ou=users,{BASE_DN}",
        search_filter=f"(uid={username})",
        search_scope=SUBTREE,
        attributes=["uid"]
    )

    if conn.entries:
        return conn.entries[0].entry_dn
    return None


def ldap_authenticate(username: str, password: str) -> bool:
    user_dn = get_user_dn(username)
    if not user_dn:
        print(f"[LDAP] Usuario {username} no encontrado.")
        return False

    try:
        server = Server(LDAP_SERVER, get_info=ALL)
        conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        return True
    except Exception as e:
        print(f"[LDAP] Error autenticando {user_dn}: {e}")
        return False


def get_user_groups(username: str) -> list[str]:
    user_dn = get_user_dn(username)
    if not user_dn:
        return []

    server = Server(LDAP_SERVER, get_info=ALL)
    conn = Connection(server, user=ADMIN_DN, password=ADMIN_PASSWORD, auto_bind=True)

    conn.search(
        search_base=f"ou=groups,{BASE_DN}",
        search_filter=f"(member={user_dn})",
        search_scope=SUBTREE,
        attributes=["cn"]
    )

    return [entry.cn.value for entry in conn.entries]
