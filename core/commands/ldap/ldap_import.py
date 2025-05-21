import os
import json
import subprocess
from core.utils.colors import red, green, blue, yellow
from core.utils.path import resolve_path

def detect_file_type(file_path: str):
    ext = os.path.splitext(file_path)[-1].lower()
    if ext == ".ldif":
        return "ldif"
    elif ext == ".json":
        return "json"
    elif ext == ".csv":
        return "csv"
    return None

def run_ldif_native(ldif_path, host, bind_dn, bind_password, mode):
    if not os.path.isfile(ldif_path):
        print(red(f"❌ File not found: {ldif_path}"))
        return 1

    url = host if host.startswith("ldap://") or host.startswith("ldaps://") else f"ldap://{host}"
    cmd = [
        "ldapmodify",
        "-x",
        "-H", url,
        "-D", bind_dn,
        "-w", bind_password,
        "-f", ldif_path,
    ]
    if mode == "add":
        cmd.insert(1, "-a")

    print(blue(f"🔧 Running: {' '.join(cmd)}\n"))

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(green("✅ Operation completed successfully"))
        return 0
    else:
        print(red("❌ ldapmodify failed"))
        if result.stderr:
            print(yellow(result.stderr.strip()))
        return result.returncode

def run(args):
    anchor = args.anchor

    mode = None
    if args.add:
        mode = "add"
    elif args.modify:
        mode = "modify"
    elif args.delete:
        mode = "delete"

    if not mode:
        print(red("❌ Must specify one of: --add, --modify or --delete"))
        return 1

    input_file = args.ldif or args.json or args.csv
    if not input_file:
        print(red("❌ No input file specified. Use --ldif, --json, or --csv"))
        return 1

    file_type = detect_file_type(input_file)
    if file_type != "ldif":
        print(yellow(f"⚠️  File type '{file_type}' not supported yet. Only LDIF is implemented."))
        return 1

    # Cargar anchor
    anchor_path = resolve_path(f"~/.anchors/data/{anchor}.json")
    if not os.path.isfile(anchor_path):
        print(red(f"❌ Anchor not found: {anchor_path}"))
        return 1

    with open(anchor_path) as f:
        meta = json.load(f)

    if meta.get("type") != "ldap":
        print(red("❌ This anchor is not of type 'ldap'"))
        return 1

    host = meta.get("host")
    bind_dn = meta.get("bind_dn")
    bind_password = meta.get("bind_password")

    if not all([host, bind_dn, bind_password]):
        print(red("❌ Missing LDAP connection details in anchor"))
        return 1

    return run_ldif_native(input_file, host, bind_dn, bind_password, mode)
