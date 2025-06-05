import os
import json
from collections import OrderedDict
from datetime import datetime, timezone
from core.utils.colors import red, green, cyan, yellow, bold

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def generate_workflow_skeleton(name):
    return OrderedDict({
        "type": "workflow",
        "name": name,
        "vars": OrderedDict({}),
        "workflow": OrderedDict({
            "tasks": [
                {
                    "id": "task_1",
                    "name": "",
                    "shell": ""
                },
                {
                    "id": "task_2",
                    "name": "",
                    "shell": ""
                }
            ]
        }),
        "groups": [],
        "meta": {
            "created_by": os.environ.get("USER", "unknown"),
            "created_at": now_iso()
        }
    })

def run(args):
    name = args.workflow
    if not name:
        print(red("❌ Usage: anc set --workflow <name>"))
        return

    if name.endswith(".json"):
        name = name[:-5]

    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    os.makedirs(anchor_dir, exist_ok=True)
    meta_path = os.path.join(anchor_dir, f"{name}.json")

    if os.path.exists(meta_path):
        print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
        confirm = input("Overwrite? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print(red("❌ Aborted. Anchor not overwritten."))
            return

    meta = generate_workflow_skeleton(name)

    try:
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(green(f"✅ Workflow anchor '{bold(name)}' created at {cyan(meta_path)}"))
    except Exception as e:
        print(red(f"❌ Failed to write anchor: {e}"))
