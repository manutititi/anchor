import os
import subprocess
from datetime import datetime, timezone
from collections import OrderedDict


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_git_branches(path):
    try:
        return subprocess.check_output(
            ["git", "-C", path, "branch", "--format=%(refname:short)"]
        ).decode().splitlines()
    except Exception:
        return []


def detect_git_metadata(path):
    try:
        root = subprocess.check_output(
            ["git", "-C", path, "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL
        ).decode().strip()

        branch = subprocess.check_output(
            ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"]
        ).decode().strip()

        commit = subprocess.check_output(
            ["git", "-C", path, "log", "-1", "--pretty=format:%H%n%an%n%ad%n%s"]
        ).decode().split("\n")

        tags = subprocess.check_output(
            ["git", "-C", path, "tag", "--points-at", "HEAD"]
        ).decode().split()

        remotes_raw = subprocess.check_output(
            ["git", "-C", path, "remote", "-v"]
        ).decode().strip().split("\n")

        remotes = []
        seen = set()
        for line in remotes_raw:
            parts = line.split()
            if len(parts) >= 2:
                key = (parts[0], parts[1])
                if key not in seen:
                    seen.add(key)
                    remotes.append({"name": parts[0], "url": parts[1]})

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


def detect_docker_metadata(path):
    compose_file = os.path.join(path, "docker-compose.yml")
    if not os.path.isfile(compose_file):
        return {"active": False}

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
        return {"active": True, "compose_file": compose_file, "services": []}
