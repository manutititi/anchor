import os
import json
from core.utils.filter import matches_filter

def color(text, code):
    return f"\033[{code}m{text}\033[0m"

def basename_no_ext(filename):
    return os.path.splitext(filename)[0]

def list_envs(folder, filter_str=None):
    found = False
    print(color(f"📌 Anchors from envs/:", "1;34"))
    for filename in sorted(os.listdir(folder)):
        path = os.path.join(folder, filename)
        if not os.path.isfile(path):
            continue

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Error reading {filename}: {e}")
            continue

        if not matches_filter(data, filter_str):
            continue

        name = basename_no_ext(filename)
        print(f"  ⚓ {color(name, '1;36')}")
        found = True

    if not found:
        print(color("  (⚠️ no matching anchors found)", "0;33"))

def list_urls(folder, filter_str=None):
    found = False
    print(color(f"📌 Anchors from urls/:", "1;34"))
    for filename in sorted(os.listdir(folder)):
        path = os.path.join(folder, filename)
        if not os.path.isfile(path):
            continue

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Error reading {filename}: {e}")
            continue

        if not matches_filter(data, filter_str):
            continue

        name = data.get("name") or basename_no_ext(filename)
        base_url = data.get("endpoint", {}).get("base_url", "")
        note = data.get("note") or data.get("meta", {}).get("note", "")

        name_fmt = color(f"⚓ {name:<20}", "1;36")
        url_fmt = color(base_url or "(no base_url)", "0;32" if base_url else "0;31")
        if note:
            print(f"  {name_fmt} → {url_fmt:<40} --------> 📝 {note}")
        else:
            print(f"  {name_fmt} → {url_fmt}")
        found = True

    if not found:
        print(color("  (⚠️ no matching anchors found)", "0;33"))

def list_generic(folder, filter_str=None):
    found = False
    print(color(f"📌 Anchors from data/:", "1;34"))
    for filename in sorted(os.listdir(folder)):
        path = os.path.join(folder, filename)
        if not os.path.isfile(path):
            continue

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Error reading {filename}: {e}")
            continue

        if not matches_filter(data, filter_str):
            continue

        name = basename_no_ext(filename)
        anchor_path = data.get("path", "")
        note = data.get("note") or data.get("meta", {}).get("note", "")

        name_fmt = color(f"⚓ {name:<20}", "1;36")
        path_fmt = color(anchor_path or "(no path)", "0;32" if anchor_path else "0;31")
        if note:
            print(f"  {name_fmt} → {path_fmt:<40} --------> 📝 {note}")
        else:
            print(f"  {name_fmt} → {path_fmt}")
        found = True

    if not found:
        print(color("  (⚠️ no matching anchors found)", "0;33"))

def run(args):
    if args.url:
        list_urls(args.url_dir, args.filter)
    elif args.env:
        list_envs(args.env_dir, args.filter)
    else:
        list_generic(args.anchor_dir, args.filter)
