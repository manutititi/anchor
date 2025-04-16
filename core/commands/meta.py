import os
import json
from pathlib import Path

from core.utils.filter import filter_anchors
from core.utils.colors import red, green, yellow, bold  # ✅ estilo directo

def set_nested(data, dotted_key, value):
    keys = dotted_key.split(".")
    current = data
    for i, key in enumerate(keys):
        if key.isdigit(): key = int(key)
        if i == len(keys) - 1:
            if isinstance(key, int) and isinstance(current, list):
                while len(current) <= key:
                    current.append(None)
                current[key] = value
            else:
                current[key] = value
        else:
            next_key = keys[i+1]
            is_next_index = next_key.isdigit()
            if isinstance(key, int):
                while len(current) <= key:
                    current.append({} if not is_next_index else [])
                if current[key] is None:
                    current[key] = {} if not is_next_index else []
                current = current[key]
            else:
                if key not in current or not isinstance(current[key], (dict, list)):
                    current[key] = {} if not is_next_index else []
                current = current[key]

def delete_nested(data, dotted_key):
    keys = dotted_key.split(".")
    current = data
    for i, key in enumerate(keys[:-1]):
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit():
            key = int(key)
            if key < len(current):
                current = current[key]
            else:
                return
        else:
            return
        if current is None:
            return
    last_key = keys[-1]
    if isinstance(current, dict) and last_key in current:
        del current[last_key]
    elif isinstance(current, list) and last_key.isdigit():
        idx = int(last_key)
        if 0 <= idx < len(current):
            current[idx] = None

def run(args):
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    deletions = args.delete or []
    filter_str = args.filter
    names = []
    updates = []

    anchor = None
    for entry in args.args:
        if "=" in entry:
            updates.append(entry)
        elif not anchor:
            anchor = entry

    if filter_str:
        anchors = filter_anchors(filter_str)
        if not anchors:
            print(yellow("⚠️ No anchors matched the filter"))
            return
        names = list(anchors.keys())
    else:
        if not anchor or (not updates and not deletions):
            print(yellow("Usage: anc meta <anchor> key=value [...] [--del key [...]]"))
            return
        names = [anchor]

    for name in names:
        anchor_path = Path(anchor_dir) / f"{name}.json"
        if not anchor_path.exists():
            print(red(f"❌ Anchor '{name}' not found"))
            continue

        try:
            with open(anchor_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(red(f"❌ Failed to read {name}: {e}"))
            continue

        for pair in updates:
            if "=" not in pair:
                print(red(f"❌ Invalid format (expected key=value): {pair}"))
                continue
            key, val = pair.split("=", 1)
            set_nested(data, key.strip(), val.strip())

        for key in deletions:
            delete_nested(data, key.strip())

        try:
            with open(anchor_path, "w") as f:
                json.dump(data, f, indent=2)
            print(green(f"✅ Metadata updated for anchor '{bold(name)}'"))
        except Exception as e:
            print(red(f"❌ Failed to write anchor '{name}': {e}"))
