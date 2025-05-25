import json
import requests
from pathlib import Path
from getpass import getpass
from core.utils.colors import red, green, yellow, blue

def run(args):
    if not args.id:
        print(red("You must provide the secret ID: `anc secret update <id>`"))
        return

    ref_id = args.id
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

    # 📥 Obtener datos actuales del secreto
    try:
        url_get = f"{server_url.rstrip('/')}/ref/pull/{ref_id}"
        res = requests.get(url_get, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if res.status_code != 200:
            print(red(f"❌ Failed to fetch current secret info: {res.status_code} {res.text}"))
            return
        current = res.json()
    except requests.exceptions.RequestException as e:
        print(red(f"Connection error:\n{e}"))
        return

    update_data = {"id": ref_id}
    print(blue(f"\n🔧 Updating secret: {ref_id}"))

    # Descripción
    current_desc = current.get("description", "")
    desc = input(
        f"📝 Description [{current_desc}]:\n"
        f"   → Enter new description to change\n"
        f"   → Leave blank to keep current\n> "
    ).strip()
    if desc:
        update_data["description"] = desc

    # Grupos
    current_groups = current.get("groups", [])
    g_prompt = input(
        f"\n👥 Groups {current_groups}:\n"
        f"   → Comma-separated list to change\n"
        f"   → Enter '-' to clear groups\n"
        f"   → Leave empty to keep current\n> "
    ).strip()
    if g_prompt == "-":
        update_data["groups"] = []
    elif g_prompt:
        update_data["groups"] = [g.strip() for g in g_prompt.split(",") if g.strip()]

    # Usuarios
    current_users = current.get("users", [])
    u_prompt = input(
        f"\n👤 Users {current_users}:\n"
        f"   → Comma-separated list to change\n"
        f"   → Enter '-' to clear users\n"
        f"   → Leave empty to keep current\n> "
    ).strip()
    if u_prompt == "-":
        update_data["users"] = []
    elif u_prompt:
        update_data["users"] = [u.strip() for u in u_prompt.split(",") if u.strip()]

    # Advertencia de seguridad
    if update_data.get("groups", current_groups) == [] and update_data.get("users", current_users) == []:
        print(yellow("⚠️  Warning: This secret will only be accessible by the creator."))

    # Valor secreto
    if input("\n🔐 Change secret value? [y/N]: ").lower() == "y":
        plaintext = getpass("New secret value (input hidden): ")
        update_data["plaintext"] = plaintext

    # allow_group_edit
    current_agg = current.get("allow_group_edit", True)
    agg = input(
        f"\n🔒 Allow group edit? [current: {current_agg}] (y/n, leave blank to keep): "
    ).strip().lower()
    if agg in ("y", "n"):
        update_data["allow_group_edit"] = (agg == "y")

    # Delegar propiedad
    current_owner = current.get("created_by")
    new_owner = input(
        f"\n👑 Current owner: {current_owner}\n"
        f"   → To delegate ownership, enter new username\n"
        f"   → Leave blank to keep current\n> "
    ).strip()
    if new_owner:
        update_data["created_by"] = new_owner

    if len(update_data.keys()) == 1:
        print(yellow("Nothing to update."))
        return

    url = f"{server_url.rstrip('/')}/ref/update"
    try:
        res = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            data=json.dumps(update_data),
            timeout=5
        )
        if res.status_code != 200:
            print(red(f"❌ Server error: {res.status_code} {res.text}"))
            return
    except requests.exceptions.RequestException as e:
        print(red(f"Connection error:\n{e}"))
        return

    print(green(f"\n✅ Secret '{ref_id}' updated successfully."))
