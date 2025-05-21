import os
import json
from collections import OrderedDict
from datetime import datetime, timezone

from core.utils.colors import red, green, cyan, yellow, bold


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def generate_ansible_metadata(name, templates):
    tasks = []

    for t in templates:
        if t.startswith("from_anchor:"):
            anchor_name = t.split(":", 1)[1]
            tasks.append({
                "template": "from_anchor",
                "vars": {"anchor": anchor_name},
                "override": {}
            })
        else:
            tasks.append({
                "template": t,
                "vars": {},
                "override": {}
            })

    return OrderedDict({
        "type": "ansible",
        "name": name,
        "groups": [],
        "ansible": {
            "tasks": tasks,
            "options": ["-v"]
        },
        "meta": {
            "created_by": os.environ.get("USER", "unknown"),
            "created_at": now_iso()
        }
    })


def run(args):
    name = args.ansible
    if not name:
        print(red("❌ Usage: anc set --ansible <name> [--templates ...]"))
        return

    templates = args.templates or ["update_upgrade"]

    if name.endswith(".json"):
        name = name[:-5]

    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    os.makedirs(anchor_dir, exist_ok=True)
    filename = f"{name}.json"
    meta_path = os.path.join(anchor_dir, filename)

    if os.path.exists(meta_path):
        print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
        confirm = input("Overwrite? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print(red("❌ Aborted. Anchor not overwritten."))
            return

    meta = generate_ansible_metadata(name, templates)

    try:
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(green(f"✅ Ansible anchor '{bold(name)}' created at {cyan(meta_path)}"))
    except Exception as e:
        print(red(f"❌ Failed to write anchor: {e}"))
