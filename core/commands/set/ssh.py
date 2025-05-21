import os
import json
import subprocess
from collections import OrderedDict
from datetime import datetime, timezone

from core.utils.colors import red, green, yellow, cyan, bold


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_user_host_path(value):
    if "@" not in value:
        raise ValueError("Format must be user@host[:/path]")

    if ":" in value:
        user_host, path = value.split(":", 1)
    else:
        user_host = value
        path = "/"

    if "/" in user_host:
        raise ValueError("Invalid format: host should not contain '/' — use user@host:/path")

    user, host = user_host.split("@", 1)
    return user, host, path


def test_connection(user, host, remote_path, identity=None, port=22):
    
    remote_test = "test -d \"$HOME\"" if remote_path == "~" else f"test -d '{remote_path}'"
    cmd = ["ssh", f"{user}@{host}", "-p", str(port), remote_test]

    if identity:
        cmd.insert(1, "-i")
        cmd.insert(2, identity)
    return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def generate_ssh_metadata(name, user, host, path, identity=None, port=22):
    meta = OrderedDict()
    meta["type"] = "ssh"
    meta["name"] = name
    meta["groups"] = []
    meta["host"] = host
    meta["user"] = user
    meta["identity"] = identity or ""
    meta["port"] = port
    meta["paths"] = [{
        "path": path,
        "note": "main remote path",
        "read_only": False,
        "tags": []
    }]
    meta["ansible"] = {
        "inventory_group": "",
        "connection": "ssh",
        "become": True,
        "vars": {},
        "templates": []
    }
    meta["scripts"] = {
        "preload": [],
        "postload": []
    }
    meta["monitoring"] = {
        "enabled": False,
        "tags": [],
        "methods": {
            "ping": True,
            "ssh_check": True,
            "custom": []
        }
    }
    meta["backups"] = {
        "enabled": False,
        "schedule": "daily",
        "paths": [],
        "retention_days": 7
    }
    meta["meta"] = {
        "created_by": os.environ.get("USER", "unknown"),
        "created_at": now_iso(),
        "description": "",
        "tags": [],
        "location": "",
        "environment": "",
        "project": ""
    }
    return meta


def run(args):
    if not args.ssh or len(args.ssh) != 2:
        print(red("Usage: anc set --ssh <name> user@host[:/path] [-i key] [--port N]"))
        return

    name = args.ssh[0]
    target = args.ssh[1]
    identity = args.identity
    port = int(args.port or 22)

    try:
        user, host, remote_path = parse_user_host_path(target)
    except ValueError as e:
        print(red(f"❌ {e}"))
        return

    print(cyan(f"🔌 Testing SSH connection to {bold(user + '@' + host)}..."))

    if not test_connection(user, host, remote_path, identity, port):
        print(red(f"❌ Could not connect or directory does not exist: {remote_path}"))
        return

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

    data = generate_ssh_metadata(name, user, host, remote_path, identity, port)

    with open(meta_path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)

    print(green(f"✅ SSH anchor '{bold(name)}' created for {user}@{host}:{remote_path}"))
