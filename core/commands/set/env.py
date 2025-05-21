import os
import json
from collections import OrderedDict

from core.utils.colors import red, green, blue, yellow, bold, cyan
from core.commands.set.common import now_iso


def parse_env_file(env_path):
    env_vars = {}
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip().strip('"').strip("'")
    return env_vars


def generate_env_metadata(name, env_vars=None):
    return OrderedDict({
        "type": "env",
        "name": name,
        "groups": [],
        "vars": env_vars or {
            "API_TOKEN": "",
            "DB_URL": "",
            "SECRET_KEY": "",
            "BASE_URL": "",
            "ENV": ""
        },
        "scripts": {
            "preload": [],
            "postload": []
        },
        "meta": {
            "created_by": os.environ.get("USER", "unknown"),
            "created_at": now_iso(),
            "description": "",
            "tags": [],
            "shared": False,
            "encrypted": False
        }
    })


def run(args):
    name = args.name
    if not name:
        print(red("❌ Usage: anc set --env <name> [.env_file]"))
        return

    if name.endswith(".json"):
        name = name[:-5]

    filename = f"{name}.json"
    meta_path = os.path.join(args.anchor_dir, filename)

    if os.path.exists(meta_path):
        print(yellow(f"⚠️  Environment already exists: {meta_path}"))
        print(red("❌ Use 'anc meta' to modify it."))
        return

    env_vars = {}
    if args.base_url:
        env_file = os.path.abspath(args.base_url)
        if not os.path.isfile(env_file):
            print(red(f"❌ File '{env_file}' not found."))
            return
        env_vars = parse_env_file(env_file)

    data = generate_env_metadata(name, env_vars)

    with open(meta_path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)

    print(green(f"✅ Environment '{bold(name)}' created at {cyan(meta_path)}"))

    with open(".anc_env", "w") as f:
        f.write(name)
    print(blue(f"📎 Linked current directory to env '{bold(name)}' via .anc_env"))
