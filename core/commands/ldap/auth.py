import json
import ldap3
import os
from core.utils.colors import green, red, cyan
from core.utils.path import resolve_path
import getpass




def run(args):
    anchor_name = args.anchor
    username = args.username
    password = args.password or getpass.getpass(f"🔑 Password for {username}: ")

    path = resolve_path(f"~/.anchors/data/{anchor_name}.json")
    if not os.path.isfile(path):
        print(red(f"❌ Anchor not found: {path}"))
        return

    with open(path, "r") as f:
        meta = json.load(f)

    if meta.get("type") != "ldap":
        print(red("❌ This anchor is not of type 'ldap'"))
        return

    host = meta["host"]
    base_dn = meta["base_dn"]
    user_dn_template = meta.get("user_filter", "(uid={username})")
    user_base = meta.get("user_dn", base_dn)
    full_filter = user_dn_template.replace("{username}", username)

    # Buscar DN real del usuario
    server = ldap3.Server(host, get_info=ldap3.NONE)
    conn = ldap3.Connection(server, user=meta["bind_dn"], password=meta["bind_password"], auto_bind=True)

    conn.search(user_base, full_filter, attributes=["dn"])
    if not conn.entries:
        print(red(f"❌ User '{username}' not found in LDAP"))
        return

    user_dn = conn.entries[0].entry_dn
    conn.unbind()

    # Intentar bind como el usuario
    try:
        user_conn = ldap3.Connection(server, user=user_dn, password=password, auto_bind=True)
        user_conn.unbind()
        print(green(f"✅ Auth OK for {cyan(user_dn)}"))
    except ldap3.core.exceptions.LDAPBindError:
        print(red("❌ Invalid credentials"))
