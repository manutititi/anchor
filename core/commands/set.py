import os
import json
from datetime import datetime
import subprocess
from collections import OrderedDict

def color(text, code): return f"\033[{code}m{text}\033[0m"
def bold(text): return color(text, "1")
def green(text): return color(text, "0;32")
def blue(text): return color(text, "1;34")
def cyan(text): return color(text, "1;36")
def yellow(text): return color(text, "0;33")
def red(text): return color(text, "0;31")

def realpath(p):
    return os.path.abspath(os.path.expanduser(p or "."))

def detect_git_metadata(path):
    try:
        root = subprocess.check_output(["git", "-C", path, "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL).decode().strip()
        branch = subprocess.check_output(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        commit = subprocess.check_output(["git", "-C", path, "log", "-1", "--pretty=format:%H%n%an%n%ad%n%s"]).decode().split("\n")
        tags = subprocess.check_output(["git", "-C", path, "tag", "--points-at", "HEAD"]).decode().split()
        remotes_raw = subprocess.check_output(["git", "-C", path, "remote", "-v"]).decode().strip().split("\n")

        remotes = []
        seen = set()
        for line in remotes_raw:
            parts = line.split()
            if len(parts) >= 2:
                key = (parts[0], parts[1])
                if key not in seen:
                    seen.add(key)
                    remotes.append({ "name": parts[0], "url": parts[1] })

        is_dirty = subprocess.call(["git", "-C", path, "diff", "--quiet"]) != 0

        return {
            "root": root,
            "branch": branch,
            "branches": get_git_branches(path),
            "tags": tags,
            "remotes": remotes,
            "is_dirty": is_dirty,
            "commit": {
                "hash": commit[0],
                "author": commit[1],
                "date": commit[2],
                "message": commit[3]
            },
            "set_branch": branch
        }
    except Exception:
        return {}

def get_git_branches(path):
    try:
        branches = subprocess.check_output(["git", "-C", path, "branch", "--format=%(refname:short)"]).decode().splitlines()
        return branches
    except Exception:
        return []

def detect_docker_metadata(path):
    compose_file = os.path.join(path, "docker-compose.yml")
    if not os.path.isfile(compose_file):
        return { "active": False }

    try:
        import yaml
        with open(compose_file, "r") as f:
            data = yaml.safe_load(f)
        services = [{"name": name, **details} for name, details in data.get("services", {}).items()]
        return {
            "active": True,
            "compose_file": compose_file,
            "services": services
        }
    except Exception:
        return { "active": True, "compose_file": compose_file, "services": [] }

def generate_local_metadata(path):
    meta = OrderedDict()
    meta["type"] = "local"
    meta["path"] = path
    meta["created_at"] = datetime.utcnow().isoformat() + "Z"

    git = detect_git_metadata(path)
    if git:
        meta["git"] = git

    docker = detect_docker_metadata(path)
    if docker.get("active"):
        meta["docker"] = docker

    return meta

def generate_url_metadata(name, base_url):
    meta = OrderedDict()
    meta["type"] = "url"
    meta["name"] = name
    meta["meta"] = {
        "project": "",
        "env": "",
        "note": "",
        "created_by": os.environ.get("USER", "unknown"),
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    meta["endpoint"] = {
        "base_url": base_url,
        "version": "v1",
        "auth": {
            "enabled": False,
            "type": "bearer",
            "token_env": "API_TOKEN"
        },
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
        "routes": []
    }
    meta["interfaces"] = {
        "docs": "",
        "dashboard": ""
    }
    meta["automation"] = {
        "test_enabled": True,
        "scan_enabled": False,
        "tools": []
    }
    meta["scripts"] = {
        "preload": [],
        "postload": []
    }
    return meta

def generate_env_metadata(name, env_vars=None):
    return OrderedDict({
        "type": "env",
        "name": name,
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
            "created_at": datetime.utcnow().isoformat() + "Z",
            "description": "",
            "tags": [],
            "shared": False,
            "encrypted": False
        }
    })

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

def run(args):
    os.makedirs(args.anchor_dir, exist_ok=True)

    if args.env:
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

        with open(".anc-env", "w") as f:
            f.write(name)
        print(blue(f"📎 Linked current directory to env '{bold(name)}' via .anc-env"))
        return

    if args.url:
        name = args.name
        base_url = args.base_url

        if not name or not base_url:
            print(red("❌ Usage: anc set --url <name> <base_url>"))
            return

        if name.endswith(".json"):
            name = name[:-5]

        filename = f"{name}.json"
        meta_path = os.path.join(args.anchor_dir, filename)

        if os.path.exists(meta_path):
            print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
            print(red("❌ Use 'anc meta' or 'anc add-route' to modify it."))
            return

        meta = generate_url_metadata(name, base_url)
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, sort_keys=False)

        print(green(f"✅ Anchor '{bold(name)}' created as type '{cyan('url')}'"))
        print(blue(f"🌐 Base URL: {base_url}"))
        return

    input_val = args.name
    if not input_val or input_val.startswith("/") or input_val.startswith(".") or os.path.isdir(input_val):
        path = realpath(input_val)
        name = os.path.basename(path)
    else:
        name = input_val
        path = os.getcwd()

    if name.endswith(".json"):
        name = name[:-5]

    filename = f"{name}.json"
    meta_path = os.path.join(args.anchor_dir, filename)

    if os.path.exists(meta_path):
        print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
        confirm = input("Overwrite? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print(red("❌ Aborted. Anchor not overwritten."))
            return

    meta = generate_local_metadata(path)
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=False)

    print(cyan(f"⚓ Anchor '{bold(name)}'") + cyan(" set to: ") + green(path))

    if "git" in meta:
        g = meta["git"]
        print(blue("🔍 Git repository detected:"))
        print(f"  {cyan('Branch:')} {g['branch']}")
        print(f"  {cyan('Root:')} {g['root']}")
        print(f"  {cyan('Last commit:')} {g['commit']['message']}")
        if g.get("is_dirty"):
            print(red("  ⚠️ Working directory has uncommitted changes"))

    if "docker" in meta and meta["docker"].get("active"):
        print(blue("🐳 Docker Compose detected:"))
        print(f"  {cyan('Services:')}")
        for s in meta["docker"].get("services", []):
            print(f"    - {s.get('name')}")
