import json
import requests
from pathlib import Path
from core.utils.colors import red, green, blue, yellow, gray

def run(args):
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

    url = f"{server_url.rstrip('/')}/ref/list"

    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
    except requests.exceptions.RequestException as e:
        print(red(f"Connection error:\n{e}"))
        return

    if response.status_code != 200:
        print(red(f"Server error: {response.status_code} {response.text}"))
        return

    secrets = response.json()
    if not secrets:
        print(yellow("No secrets found."))
        return

    print(green("Secrets (ref):"))
    for secret in secrets:
        id_ = secret.get("id", "")
        desc = secret.get("description", "")
        print(f"  🔐 {blue(id_):<20} → {gray(desc)}")
