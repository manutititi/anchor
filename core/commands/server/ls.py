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

    try:
        response = requests.get(
            f"{server_url}/db/list",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
    except requests.exceptions.RequestException as e:
        print(red(f"Connection error:\n{e}"))
        return

    if response.status_code != 200:
        print(red(f"Server error: {response.status_code} {response.text}"))
        return

    anchors = response.json()
    if not anchors:
        print(yellow("No anchors found."))
        return

    print(green("Anchors (remote):"))

    for anchor in anchors:
        name = anchor.get("name", "")
        type_ = anchor.get("type", "")
        path = anchor.get("path") or anchor.get("endpoint", {}).get("base_url") or "(no path)"
        updated = anchor.get("last_updated", "")

        type_fmt = f"[{type_}]"
        path_fmt = gray(path)
        updated_fmt = gray(updated)

        print(f"  ⚓ {blue(name):<20} {type_fmt:<10} → {path_fmt:<40} {updated_fmt}")
