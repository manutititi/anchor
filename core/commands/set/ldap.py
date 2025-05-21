import os
import json
from collections import OrderedDict

from core.utils.colors import red, green, blue, cyan, yellow, bold
from core.commands.set.common import now_iso


def generate_ldap_metadata(name, host, base_dn, bind_dn, bind_password):
    return OrderedDict({
        "type": "ldap",
        "name": name,
        "groups": [],
        "host": host,
        "base_dn": base_dn,
        "bind_dn": bind_dn,
        "bind_password": bind_password,
        "user_dn": f"ou=users,{base_dn}",
        "group_dn": f"ou=groups,{base_dn}",
        "user_filter": "(uid={username})",
        "group_filter": "(member={user_dn})",
        "attributes": {
            "uid": "username",
            "cn": "fullname",
            "sn": "surname",
            "memberOf": "groups"
        },
        "tls": host.startswith("ldaps://"),
        "meta": {
            "created_by": os.environ.get("USER", "unknown"),
            "created_at": now_iso(),
            "description": "LDAP anchor",
            "tags": []
        }
    })


def prompt(msg, default):
    val = input(f"{msg} [{default}]: ").strip()
    return val or default


def run(args):
    name = args.name
    if not name:
        print(red("❌ Usage: anc set --ldap <name>"))
        return

    if name.endswith(".json"):
        name = name[:-5]

    filename = f"{name}.json"
    meta_path = os.path.join(args.anchor_dir, filename)

    if os.path.exists(meta_path):
        print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
        confirm = input("Overwrite? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print(red("❌ Aborted. Anchor not overwritten."))
            return

    host = args.base_url or prompt("LDAP host URL", "ldap://localhost:8389")
    base_dn = args.base_dn or prompt("Base DN", "dc=anchor,dc=local")
    bind_dn = args.bind_dn or prompt("Bind DN", f"cn=admin,{base_dn}")
    bind_password = args.bind_password or prompt("Bind password", "admin")

    meta = generate_ldap_metadata(name, host, base_dn, bind_dn, bind_password)

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=False)

    print(green(f"✅ LDAP anchor '{bold(name)}' created"))
    print(blue(f"🔗 Host: {cyan(host)}"))
    print(f"  {cyan('Base DN:')} {base_dn}")
    print(f"  {cyan('Bind DN:')} {bind_dn}")
