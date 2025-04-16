import os
import json

from core.utils.filter import filter_anchors
from core.utils.colors import cyan, blue, green, red, yellow, magenta, gray, dim

def basename_no_ext(filename):
    return os.path.splitext(filename)[0]

def run(args):
    folder = args.anchor_dir
    if not os.path.isdir(folder):
        print(red(f"❌ Anchor directory not found: {folder}"))
        return

    filter_str = args.filter
    filter_type = "url" if args.url else "env" if args.env else None

    all_filtered = filter_anchors(filter_str)
    found = False

    print(blue("Anchors:"))

    for name, data in sorted(all_filtered.items()):
        if filter_type and data.get("type") != filter_type:
            continue

        type_ = data.get("type", "unknown")
        note = data.get("note") or data.get("meta", {}).get("note", "")
        info = ""

        if type_ == "url":
            info = data.get("endpoint", {}).get("base_url", "")
        elif type_ in ["local", "file", "ssh"]:
            info = data.get("path", "")
        elif type_ == "env":
            info = "env"

        type_color_fn = {
            "url": cyan,
            "env": magenta,
            "local": blue,
            "ssh": blue,
            "file": yellow
        }.get(type_, gray)

        name_fmt = cyan(f"⚓ {name:<20}")
        type_fmt = type_color_fn(f"[{type_}]")
        info_fmt = green(info) if info else red("(no path)")

        if note:
            print(f"  {name_fmt} {type_fmt} → {info_fmt:<30} {yellow('📝 ' + note)}")
        else:
            print(f"  {name_fmt} {type_fmt} → {info_fmt}")
        found = True

    if not found:
        print(yellow("  (⚠️ no matching anchors found)"))
