import json
import requests
from pathlib import Path
from getpass import getpass
from core.utils.colors import red, green, yellow, blue

MAX_SIZE = 100 * 1024  # 100 KB

def run(args):
    ref_id = args.id
    file_arg = args.file
    flags_used = any([args.desc, args.users, args.groups, args.secret, args.gedit])

    # ⚠️ Validación exclusiva
    if file_arg and args.secret:
        print(red("❌ You cannot use both a file and --secret at the same time."))
        return

    if not ref_id:
        print(red("❌ You must provide a secret ID: `anc secret push <id> [file]`"))
        return

    # 📡 Cargar config del servidor
    info_path = Path.home() / ".anchors" / "server" / "info.json"
    if not info_path.exists():
        print(red("No remote server configured. Use: anc server url <url>"))
        return

    with open(info_path) as f:
        server_info = json.load(f)

    server_url = server_info.get("url")
    token = server_info.get("token")

    if not server_url or not token:
        print(red("Missing server URL or token. Use `anc server auth` to authenticate."))
        return

    # 🔍 Comprobar si existe
    try:
        check_url = f"{server_url.rstrip('/')}/ref/exists/{ref_id}"
        res = requests.get(check_url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if res.status_code == 200:
            print(yellow(f"⚠️  Secret '{ref_id}' already exists in the server. Push aborted."))
            return
        elif res.status_code != 404:
            print(red(f"❌ Server check failed: {res.status_code} {res.text}"))
            return
    except Exception as e:
        print(red(f"Connection error while checking existence:\n{e}"))
        return

    print(blue(f"Creating new secret '{ref_id}' on the server"))

    # 🔐 Obtener contenido
    if args.secret:
        plaintext = args.secret
        print(blue("🔐 Using plaintext from --secret"))
    elif file_arg:
        file_path = Path(file_arg)
        if not file_path.exists() or not file_path.is_file():
            print(red(f"❌ File '{file_arg}' does not exist or is not a regular file."))
            return
        if file_path.stat().st_size > MAX_SIZE:
            print(red(f"❌ File exceeds size limit ({MAX_SIZE // 1024} KB)."))
            return
        with open(file_path, "r") as f:
            plaintext = f.read()
        print(blue(f"🔐 Using file as secret: {file_arg}"))
    else:
        plaintext = getpass("🔐 Secret value (hidden): ")

    # 🎛 Modo NO interactivo (flags presentes)
    if flags_used:
        description = args.desc or ""
        users = [u.strip() for u in (args.users or "").split(",") if u.strip()]
        groups = [g.strip() for g in (args.groups or "").split(",") if g.strip()]
        allow_group_edit = args.gedit
    else:
        # 🎛 Modo interactivo
        description = input("📝 Description: ").strip()
        users = input("👤 Users (comma-separated): ").strip().split(",")
        groups = input("👥 Groups (comma-separated): ").strip().split(",")
        allow_group_edit = input("🔒 Allow group edit? [Y/n]: ").lower() != "n"

    payload = {
        "id": ref_id,
        "description": description,
        "plaintext": plaintext,
        "groups": [g.strip() for g in groups if g.strip()],
        "users": [u.strip() for u in users if u.strip()],
        "allow_group_edit": allow_group_edit
    }

    try:
        res = requests.post(
            f"{server_url.rstrip('/')}/ref/set",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            data=json.dumps(payload),
            timeout=5
        )
        if res.status_code != 201:
            print(red(f"❌ Failed to push secret: {res.status_code} {res.text}"))
            return
    except Exception as e:
        print(red(f"Connection error during push:\n{e}"))
        return

    print(green(f"✅ Secret '{ref_id}' pushed successfully to the server."))
