import os
import sys
import json
from pathlib import Path

def color(text, code): return f"\033[{code}m{text}\033[0m"
def green(text): return color(text, "0;32")
def red(text): return color(text, "0;31")
def yellow(text): return color(text, "0;33")
def bold(text): return color(text, "1")

def set_nested(data, dotted_key, value):
    keys = dotted_key.split(".")
    current = data
    for i, key in enumerate(keys):
        if key.isdigit():
            key = int(key)
        if i == len(keys) - 1:
            # Última clave → asignar
            if isinstance(key, int) and isinstance(current, list):
                while len(current) <= key:
                    current.append(None)
                current[key] = value
            else:
                current[key] = value
        else:
            # Intermedio → crear dict/list si hace falta
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

def run(args):
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    anchor_name = args.anchor
    updates = args.kv_pairs

    if not anchor_name or not updates:
        print(yellow("Usage: anc meta <anchor> key=value [key=value ...]"))
        return

    if not anchor_name.endswith(".json"):
        anchor_name += ".json"

    anchor_path = Path(anchor_dir) / anchor_name
    if not anchor_path.exists():
        print(red(f"❌ Anchor '{anchor_name}' not found at {anchor_path}"))
        return

    try:
        with open(anchor_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(red(f"❌ Failed to read JSON: {e}"))
        return

    for pair in updates:
        if "=" not in pair:
            print(red(f"❌ Invalid format (expected key=value): {pair}"))
            continue
        key, val = pair.split("=", 1)
        set_nested(data, key.strip(), val.strip())

    try:
        with open(anchor_path, "w") as f:
            json.dump(data, f, indent=2)
        print(green(f"✅ Metadata updated for anchor '{bold(anchor_name)}'"))
    except Exception as e:
        print(red(f"❌ Failed to write updated anchor: {e}"))
