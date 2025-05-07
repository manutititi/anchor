import json
import os
from ldap3 import Server, Connection, SUBTREE
from core.utils.colors import green, red, cyan
from core.utils.path import resolve_path

def run(args):
    anchor = args.anchor
    path = resolve_path(f"~/.anchors/data/{anchor}.json")

    if not os.path.isfile(path):
        print(red(f"❌ Anchor not found: {path}"))
        return

    with open(path) as f:
        meta = json.load(f)

    if meta.get("type") != "ldap":
        print(red("❌ This anchor is not of type 'ldap'"))
        return

    host = meta["host"]
    bind_dn = meta["bind_dn"]
    bind_password = meta["bind_password"]
    group_dn = meta.get("group_dn", meta["base_dn"])
    group_filter = meta.get("group_filter", "(objectClass=groupOfNames)").replace("{user_dn}", "*")
    attr_map = meta.get("attributes", {})
    server = Server(host)

    conn = Connection(server, bind_dn, bind_password, auto_bind=True)

    conn.search(group_dn, group_filter, search_scope=SUBTREE, attributes=["cn", "member"])

    if not conn.entries:
        print(red("❌ No groups found"))
        return

    print(green(f"🗂️ Groups in {cyan(group_dn)}:"))
    for entry in conn.entries:
        group_name = entry["cn"].value if "cn" in entry else "Unnamed"
        members = entry["member"].values if "member" in entry else []
        print(f"• {group_name}: {len(members)} member(s)")
        for m in members:
            print(f"   - {m}")

    conn.unbind()
