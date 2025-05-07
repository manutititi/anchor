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
    user_dn = meta.get("user_dn", meta["base_dn"])
    group_dn = meta.get("group_dn", meta["base_dn"])
    user_filter = meta.get("user_filter", "(objectClass=person)").replace("{username}", "*")
    attr_map = meta.get("attributes", {})

    server = Server(host)
    conn = Connection(server, bind_dn, bind_password, auto_bind=True)

    # Buscar usuarios
    conn.search(user_dn, user_filter, search_scope=SUBTREE, attributes=list(attr_map.keys()))
    if not conn.entries:
        print(red("❌ No users found"))
        return

    users_out = []

    if not args.json:
        print(green(f"👥 Users in {cyan(user_dn)}:"))

    for entry in conn.entries:
        user_dn_actual = entry.entry_dn
        values = {}

        # Atributos definidos en el anchor
        for ldap_attr, label in attr_map.items():
            val = entry[ldap_attr].value if ldap_attr in entry else None
            if isinstance(val, list):
                val = ", ".join(val)
            values[label] = val

        # Reverse lookup de grupos
        conn.search(group_dn, f"(member={user_dn_actual})", attributes=["cn"])
        group_names = [g["cn"].value for g in conn.entries]
        values["groups"] = group_names

        if args.json:
            users_out.append(values)
        else:
            display = [f"{cyan(k)}: {v}" for k, v in values.items()]
            print("• " + " | ".join(display))

    conn.unbind()

    if args.json:
        print(json.dumps(users_out, indent=2))
