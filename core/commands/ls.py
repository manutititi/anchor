import os
import json
from core.utils.filter import matches_filter

def color(text, code): return f"\033[{code}m{text}\033[0m"
def cyan(text): return color(text, "1;36")
def green(text): return color(text, "0;32")
def red(text): return color(text, "0;31")
def yellow(text): return color(text, "0;33")
def blue(text): return color(text, "1;34")

def basename_no_ext(filename):
    return os.path.splitext(filename)[0]

def run(args):
    folder = args.anchor_dir
    if not os.path.isdir(folder):
        print(red(f"❌ Anchor directory not found: {folder}"))
        return

    filter_str = args.filter
    filter_type = "url" if args.url else "env" if args.env else None

    print(blue(f"Anchors:"))
    found = False

    for filename in sorted(os.listdir(folder)):
        if not filename.endswith(".json"):
            continue

        full_path = os.path.join(folder, filename)
        try:
            with open(full_path) as f:
                data = json.load(f)
        except Exception as e:
            print(red(f"❌ Error reading {filename}: {e}"))
            continue

        # Filtrar por tipo si se especifica --url o --env
        if filter_type and data.get("type") != filter_type:
            continue

        # Filtro por metadatos
        if filter_str and not matches_filter(data, filter_str):
            continue

        name = data.get("name") or basename_no_ext(filename)
        type_ = data.get("type", "unknown")
        note = data.get("note") or data.get("meta", {}).get("note", "")
        info = ""

        if type_ == "url":
            info = data.get("endpoint", {}).get("base_url", "")
        elif type_ == "local":
            info = data.get("path", "")
        elif type_ == "env":
            info = ""  # para env no mostramos path

        name_fmt = cyan(f"⚓ {name:<20}")
        type_fmt = blue(f"[{type_}]")
        if info:
            info_fmt = green(info)
        else:
            info_fmt = red("(no path)")

        if note:
            print(f"  {name_fmt} {type_fmt} → {info_fmt:<30} 📝 {note}")
        else:
            print(f"  {name_fmt} {type_fmt} → {info_fmt}")
        found = True

    if not found:
        print(yellow("  (⚠️ no matching anchors found)"))
