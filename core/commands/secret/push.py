import json
import requests
from pathlib import Path
from getpass import getpass
from core.utils.colors import red, green, yellow, blue

def run(args):
    if not args.id:
        print(red("You must provide a secret ID: `anc ref push <id>`"))
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

    # 📡 Check if secret already exists remotely
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

    description = input("📝 Description: ").strip()
    groups = input("👥 Groups (comma-separated): ").strip().split(",")
    users = input("👤 Users (comma-separated): ").strip().split(",")
    plaintext = getpass("🔐 Secret value (hidden): ")
    allow_group_edit = input("🔒 Allow group edit? [Y/n]: ").lower() != "n"

    payload = {
        "id": ref_id,
        "description": description,
        "groups": [g.strip() for g in groups if g.strip()],
        "users": [u.strip() for u in users if u.strip()],
        "plaintext": plaintext,
        "allow_group_edit": allow_group_edit
    }

    try:
        res = requests.post(
            f"{server_url.rstrip('/')}/ref/set",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
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
