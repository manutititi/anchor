import json
import requests
from pathlib import Path
from core.utils.colors import red, green, blue

def run(args):
    if not args.id:
        print(red("You must provide the secret ID: `anc ref pull <id>`"))
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

    url = f"{server_url.rstrip('/')}/ref/pull/{ref_id}"

    try:
        res = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if res.status_code == 404:
            print(red(f"Secret '{ref_id}' not found."))
            return
        if res.status_code == 403:
            print(red(f"Access denied to secret '{ref_id}'."))
            return
        res.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(red(f"Connection error:\n{e}"))
        return

    data = res.json()
    ref_dir = Path.home() / ".anchors" / "ref"
    ref_dir.mkdir(parents=True, exist_ok=True)

    out_path = ref_dir / f"{ref_id}.json"
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print(green(f"✅ Secret '{ref_id}' pulled successfully."))
    print(f"📦 Saved to: {blue(str(out_path))}")
