import os
import json
from collections import OrderedDict

from core.utils.colors import red, green, blue, cyan, yellow, bold
from core.utils.path import resolve_path
from core.commands.set.common import now_iso, detect_git_metadata, detect_docker_metadata


def generate_local_metadata(raw_path, stored_path, name):
    """
    Generate metadata for a local anchor, including Git and Docker info.
    'raw_path' is the absolute path used for detection.
    'stored_path' is what gets written in the metadata.
    """
    meta = OrderedDict()
    meta["type"] = "local"
    meta["name"] = name
    meta["path"] = stored_path
    meta["groups"] = []
    meta["created_at"] = now_iso()

    git = detect_git_metadata(raw_path)
    if git:
        meta["git"] = git

    docker = detect_docker_metadata(raw_path)
    if docker.get("active"):
        meta["docker"] = docker

    return meta


def run(args):
    input_val = args.name

    if not input_val or input_val.startswith("/") or input_val.startswith(".") or os.path.isdir(input_val):
        abs_path = resolve_path(input_val)
        name = os.path.basename(abs_path)
    else:
        name = input_val
        abs_path = os.getcwd()

    # Path stored in the metadata (relative or absolute)
    stored_path = abs_path
    if not args.abs and abs_path.startswith(os.path.expanduser("~")):
        stored_path = abs_path.replace(os.path.expanduser("~"), "~", 1)

    if name.endswith(".json"):
        name = name[:-5]

    filename = f"{name}.json"
    meta_path = os.path.join(args.anchor_dir, filename)

    if os.path.exists(meta_path):
        print(yellow(f"Anchor already exists: {meta_path}"))
        confirm = input("Overwrite? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print(red("Aborted. Anchor not overwritten."))
            return

    meta = generate_local_metadata(abs_path, stored_path, name)
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=False)

    print(cyan(f"Anchor '{bold(name)}' set to: ") + green(stored_path))

    if "git" in meta:
        g = meta["git"]
        print(blue("Git repository detected:"))
        print(f"  {cyan('Branch:')} {g['branch']}")
        print(f"  {cyan('Root:')} {g['root']}")
        print(f"  {cyan('Last commit:')} {g['commit']['message']}")
        if g.get("is_dirty"):
            print(red("  Warning: working directory has uncommitted changes"))

    if "docker" in meta and meta["docker"].get("active"):
        print(blue("Docker Compose detected:"))
        print(f"  {cyan('Services:')}")
        for s in meta["docker"].get("services", []):
            print(f"    - {s.get('name')}")
