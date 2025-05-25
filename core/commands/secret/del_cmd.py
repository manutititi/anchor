import json
import requests
from pathlib import Path
from core.utils.colors import red, green, yellow

def run(args):
    if not args.id:
        print(red("You must provide the secret ID: `anc secret del <id>`"))
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

    url = f"{server_url.rstrip('/')}/ref/delete/{ref_id}"
    try:
        response = requests.delete(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
    except requests.exceptions.RequestException as e:
        print(red(f"Connection error:\n{e}"))
        return

    if response.status_code == 200:
        print(green(f"✅ Secret '{ref_id}' deleted successfully."))
    elif response.status_code == 403:
        print(red("❌ Access denied: only the creator can delete this secret."))
    elif response.status_code == 404:
        print(red("❌ Secret not found."))
    else:
        print(red(f"❌ Server error: {response.status_code} {response.text}"))
