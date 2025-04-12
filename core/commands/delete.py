import os
import json
from core.utils.filter import matches_filter

def color(text, code): return f"\033[{code}m{text}\033[0m"
def bold(text): return color(text, "1")
def red(text): return color(text, "0;31")
def green(text): return color(text, "0;32")
def yellow(text): return color(text, "0;33")

def delete_anchor(path):
    try:
        os.remove(path)
        return True
    except Exception as e:
        print(red(f"❌ Failed to delete {path}: {e}"))
        return False

def run(args):
    anchor_dir = args.anchor_dir

    # 🔍 Modo filtrado
    if args.filter:
        deleted = 0
        for filename in os.listdir(anchor_dir):
            full_path = os.path.join(anchor_dir, filename)
            if not filename.endswith(".json") or not os.path.isfile(full_path):
                continue
            try:
                with open(full_path) as f:
                    data = json.load(f)
                if matches_filter(data, args.filter):
                    name = os.path.splitext(filename)[0]
                    confirm = input(yellow(f"⚠️ Delete anchor '{name}'? [y/N]: ")).strip().lower()
                    if confirm in ("y", "yes"):
                        if delete_anchor(full_path):
                            deleted += 1
            except Exception as e:
                print(red(f"❌ Error reading {filename}: {e}"))
        if deleted > 0:
            print(green(f"✅ Deleted {deleted} anchor(s)."))
        else:
            print(yellow("⚠️ No anchors deleted."))
        return

    # 🧹 Modo individual
    if not args.name:
        print(red("❌ Usage: anc del <name> or anc del -f key=value"))
        return

    filename = f"{args.name}.json"
    full_path = os.path.join(anchor_dir, filename)

    if not os.path.isfile(full_path):
        print(red(f"❌ Anchor '{args.name}' not found at {full_path}"))
        return

    confirm = input(yellow(f"⚠️ Are you sure you want to delete '{args.name}'? [y/N]: ")).strip().lower()
    if confirm in ("y", "yes"):
        if delete_anchor(full_path):
            print(green(f"✅ Anchor '{args.name}' deleted."))
