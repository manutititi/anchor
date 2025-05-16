import json
import os
from ldap3 import Server, Connection, SUBTREE
from core.utils.path import resolve_path
from core.utils.colors import cyan, red
from .ldif_export import export_ldif
from .json_export import export_json
from .csv_export import export_users, export_groups

def normalize_filter(f):
    f = f.strip()
    return f if f.startswith("(") else f"({f})"

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
    base_dn = meta["base_dn"]

    ldap_filter = normalize_filter(
        args.filter or (f"objectClass={args.cls}" if args.cls else "objectClass=*")
    )

    server = Server(host)
    conn = Connection(server, bind_dn, bind_password, auto_bind=True)
    conn.search(base_dn, ldap_filter, search_scope=SUBTREE, attributes=["*"])

    if not conn.entries:
        print(red("❌ No entries found"))
        conn.unbind()
        return

    # Exports
    if args.ldif:
        export_ldif(conn.entries, args.ldif)

    elif args.json:
        export_json(conn.entries, args.json if isinstance(args.json, str) else None)

    elif args.csv:
        output = args.csv if isinstance(args.csv, str) else "export.csv"

        # Heurística: objectClass contiene nombre común de grupos
        group_keywords = ["groupofnames", "posixgroup", "groupofuniquenames", "ipausergroup"]

        def is_group(entry):
            obj = entry["objectClass"].value if "objectClass" in entry else []
            values = [obj] if isinstance(obj, str) else obj
            return any(val.lower() in group_keywords for val in values)

        if all(is_group(e) for e in conn.entries):
            export_groups(conn.entries, member_attr="member", output=output)
        else:
            export_users(conn.entries, attr_map=None, output=output)

    else:
        # Shell  Mode
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
