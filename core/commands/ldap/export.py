import json
import os
from ldap3 import Server, Connection, SUBTREE
from core.utils.path import resolve_path

def run(args):
    anchor = args.anchor
    path = resolve_path(f"~/.anchors/data/{anchor}.json")

    if not os.path.isfile(path):
        print(f"Anchor not found: {path}")
        return

    with open(path) as f:
        meta = json.load(f)

    if meta.get("type") != "ldap":
        print("This anchor is not of type 'ldap'")
        return

    host = meta["host"]
    bind_dn = meta["bind_dn"]
    bind_password = meta["bind_password"]
    base_dn = meta["base_dn"]
    obj_class = args.cls or "*"

    server = Server(host)
    conn = Connection(server, bind_dn, bind_password, auto_bind=True)

    conn.search(base_dn, f"(objectClass={obj_class})", search_scope=SUBTREE, attributes=["*"])

    for entry in conn.entries:
        print(entry.entry_dn)
        for attr, val in entry.entry_attributes_as_dict.items():
            if isinstance(val, list):
                for item in val:
                    print(f"{attr}: {item}")
            else:
                print(f"{attr}: {val}")
        print()

    conn.unbind()
