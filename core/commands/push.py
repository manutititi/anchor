import os
import json
import requests
from core.utils.server_utils import load_server_info
from core.utils.path import resolve_path
from core.utils.colors import green, red, yellow, blue
from core.utils import filter as anchor_filter

ANCHOR_DIR = os.environ.get("ANCHOR_DIR", os.path.expanduser("~/.anchors/data"))

def push_anchor(name: str, info: dict):
    if not name.endswith(".json"):
        name += ".json"

    anchor_path = os.path.join(ANCHOR_DIR, f"{name}")
    if not os.path.isfile(anchor_path):
        print(red(f"❌ Anchor file not found: {anchor_path}"))
        return 1

    filename = os.path.basename(anchor_path)
    print(blue(f"⬆️  Uploading '{filename}'..."))

    server_url = info.get("url")
    token = info.get("token")
    if not token or not server_url:
        print(red("❌ Missing server config. Run `anc server auth`."))
        return 1

    with open(anchor_path, "r") as f:
        data = json.load(f)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    upload_url = f"{server_url}/db/upload/{filename}"

    try:
        response = requests.post(upload_url, headers=headers, json=data)
    except Exception as e:
        print(red(f"❌ Error connecting to server: {e}"))
        return 1

    if response.status_code in (200, 201):
        print(green(f"✅ '{filename}' pushed successfully"))
        return 0
    else:
        print(red(f"❌ Upload failed ({response.status_code})"))
        print(yellow("Server response:"), response.text)
        return 1

def push_command(name: str = None, filter_str: str = None):
    info = load_server_info()
    if not info:
        print(red("❌ Server not configured."))
        return 1

    if name:
        return push_anchor(name, info)

    matched = anchor_filter.filter_anchors(filter_str)
    if not matched:
        print(yellow("⚠️  No anchors matched the filter."))
        return 1

    anchor_filenames = [f"{name}.json" for name in matched]
    print(blue(f"📦 Preparing to push {len(anchor_filenames)} anchor(s):"))
    for fname in anchor_filenames:
        print(f"  - {fname}")

    print(blue("\nDo you want to proceed with the upload? [y/N] "), end="")
    confirm = input().strip().lower()
    if confirm != "y":
        print(yellow("❌ Upload cancelled by user."))
        return 0

    print(blue("\nStarting upload...\n"))


    failures = 0
    for anchor_name in matched:
        result = push_anchor(anchor_name, info)
        if result != 0:
            failures += 1

    if failures == 0:
        print(green("✅ All anchors pushed successfully"))
    else:
        print(red(f"❌ {failures} anchor(s) failed to push"))
    return failures
