import os
import json
from collections import OrderedDict

from core.utils.colors import red, green, blue, cyan, yellow, bold
from core.commands.set.common import now_iso


def generate_url_metadata(name, base_url):
    return OrderedDict({
        "type": "url",
        "name": name,
        "groups": [],
        "meta": {
            "project": "",
            "env": "",
            "note": "",
            "created_by": os.environ.get("USER", "unknown"),
            "created_at": now_iso()
        },
        "endpoint": {
            "base_url": base_url,
            "version": "v1",
            "auth": {
                "enabled": False,
                "type": "bearer",
                "token_env": "API_TOKEN"
            },
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            "routes": []
        },
        "interfaces": {
            "docs": "",
            "dashboard": ""
        },
        "automation": {
            "test_enabled": True,
            "scan_enabled": False,
            "tools": []
        },
        "scripts": {
            "preload": [],
            "postload": []
        }
    })


def run(args):
    name = args.name
    base_url = args.base_url

    if not name or not base_url:
        print(red("❌ Usage: anc set --url <name> <base_url>"))
        return

    if name.endswith(".json"):
        name = name[:-5]

    filename = f"{name}.json"
    meta_path = os.path.join(args.anchor_dir, filename)

    if os.path.exists(meta_path):
        print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
        print(red("❌ Use 'anc meta' or 'anc add-route' to modify it."))
        return

    meta = generate_url_metadata(name, base_url)

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=False)

    print(green(f"✅ Anchor '{bold(name)}' created as type '{cyan('url')}'"))
    print(blue(f"🌐 Base URL: {base_url}"))
