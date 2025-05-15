import json
import requests
from pathlib import Path
from core.utils.colors import green, red, blue, dim

def run(args):
    # Load server config
    info_path = Path.home() / ".anchors" / "server" / "info.json"
    if not info_path.exists():
        print(red("No remote server configured. Use: anc server url <url>"))
        return

    with open(info_path) as f:
        info = json.load(f)

    url = info.get("url")
    if not url:
        print(red("Missing server URL in config."))
        return

    print(dim(f"Server: {url}"))

    try:
        response = requests.get(f"{url}/health", timeout=5)
        if response.status_code != 200:
            print(red("❌ Server responded with an error"))
            print(response.text)
            return
    except Exception as e:
        print(red(f"❌ Could not reach server: {e}"))
        return

    status = response.json().get("status")
    if status == "ok":
        print(green("✅ Server is reachable and healthy"))
    else:
        print(red("⚠️ Server is reachable but db returned a failure status"))
