import json
import requests
import os
from pathlib import Path
from core.utils.colors import red, green, blue, yellow, gray
from core.utils.server_utils import load_server_info

ANCHOR_DIR = os.environ.get("ANCHOR_DIR", os.path.expanduser("~/.anchors/data"))


def pull_single(name: str, info: dict, yes: bool = False) -> int:
    if not name:
        print(red("❌ Anchor name required"))
        return 1

    server_url = info.get("url")
    token = info.get("token")
    if not token or not server_url:
        print(red("❌ Missing server config. Use `anc server auth`."))
        return 1

    output_path = Path(ANCHOR_DIR) / f"{name}.json"
    if output_path.exists() and not yes:
        print(yellow(f"⚠️  ") + green(f"{name}.json") + yellow(" already exists."))
        overwrite = input(yellow("   → Overwrite? [y/N]: "))
        if overwrite.lower() not in ["y", "yes"]:
            print(gray(f"⏭️  Skipping '{name}'"))
            return 0

    print(blue(f"⬇️  Downloading '{name}'..."))

    try:
        response = requests.get(
            f"{server_url}/db/pull/{name}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
    except Exception as e:
        print(red(f"❌ Error connecting to server: {e}"))
        return 1

    if response.status_code != 200:
        print(red(f"❌ Failed to pull '{name}' ({response.status_code})"))
        print(gray(response.text))
        return 1

    data = response.json()
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(green(f"✅ '{name}' pulled successfully"))
    return 0


def run(anchor: str = None, filter_str: str = None, all_flag: bool = False, yes: bool = False):
    info = load_server_info()
    if not info:
        print(red("❌ Server not configured. Use `anc server auth`."))
        return 1

    if anchor:
        return pull_single(anchor, info)

    if not filter_str and not all_flag:
        print(yellow("Usage: anc pull <anchor> OR anc pull -f ... OR anc pull --all"))
        return 1

    # Obtener lista de anchors desde /db/list
    try:
        params = {}
        if filter_str:
            params["filter"] = filter_str

        response = requests.get(
            f"{info['url']}/db/list",
            headers={"Authorization": f"Bearer {info['token']}"},
            params=params,
            timeout=5
        )
        response.raise_for_status()
        anchors = response.json()
    except Exception as e:
        print(red(f"❌ Failed to list anchors: {e}"))
        return 1

    if not anchors:
        print(yellow("⚠️  No anchors found matching criteria."))
        return 0

    print(blue(f"📥 {len(anchors)} anchor(s) matched:"))
    for anchor_obj in anchors:
        print(f"  ⚓ {green(anchor_obj.get('name', '(unknown)'))}")

    if not yes:
        confirm = input(yellow("❓ Do you want to pull these anchors? [y/N]: "))
        if confirm.lower() not in ["y", "yes"]:
            print(gray("⏭️  Operation cancelled."))
            return 0

    failures = 0
    for anchor_obj in anchors:
        name = anchor_obj.get("name")
        if not name:
            continue
        result = pull_single(name, info)
        if result != 0:
            failures += 1

    if failures == 0:
        print(green("✅ All anchors pulled successfully"))
    else:
        print(red(f"❌ {failures} anchor(s) failed"))

    return failures
