"""
Local metadata detectors used when creating anchors.

- detect_git(path)    → dict with branch, commit, remotes, dirty state
- detect_docker(path) → dict with services from docker-compose.yml
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def detect_git(path: str | Path) -> dict | None:
    """
    Return git metadata for the given directory, or None if not a repo.
    Runs fast git commands; silently ignores any errors.
    """
    path = str(path)
    try:
        root = subprocess.check_output(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    def _git(*args: str) -> str:
        try:
            return subprocess.check_output(
                ["git", "-C", path, *args],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except subprocess.CalledProcessError:
            return ""

    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    commit_raw = _git("log", "-1", "--pretty=format:%H%n%an%n%ad%n%s").split("\n")
    is_dirty = subprocess.call(
        ["git", "-C", path, "diff", "--quiet"],
        stderr=subprocess.DEVNULL,
    ) != 0

    remotes_raw = _git("remote", "-v").splitlines()
    remotes: list[dict] = []
    seen: set[tuple] = set()
    for line in remotes_raw:
        parts = line.split()
        if len(parts) >= 2:
            key = (parts[0], parts[1])
            if key not in seen:
                seen.add(key)
                remotes.append({"name": parts[0], "url": parts[1]})

    tags = [t for t in _git("tag", "--points-at", "HEAD").splitlines() if t]
    branches = [b for b in _git("branch", "--format=%(refname:short)").splitlines() if b]

    return {
        "root": root,
        "branch": branch,
        "is_dirty": is_dirty,
        "commit": {
            "hash":    commit_raw[0] if len(commit_raw) > 0 else "",
            "author":  commit_raw[1] if len(commit_raw) > 1 else "",
            "date":    commit_raw[2] if len(commit_raw) > 2 else "",
            "message": commit_raw[3] if len(commit_raw) > 3 else "",
        },
        "remotes": remotes,
        "tags": tags,
        "branches": branches,
    }


def detect_docker(path: str | Path) -> dict | None:
    """
    Return Docker Compose metadata if docker-compose.yml exists in path.
    Returns None if no compose file is found.
    """
    compose_file = Path(path) / "docker-compose.yml"
    if not compose_file.exists():
        return None

    try:
        import yaml  # optional dep
        with open(compose_file) as fh:
            data = yaml.safe_load(fh)
        services = [
            {"name": svc_name, **{k: v for k, v in (svc or {}).items() if k != "name"}}
            for svc_name, svc in (data.get("services") or {}).items()
        ]
        return {"active": True, "compose_file": str(compose_file), "services": services}
    except ImportError:
        # PyYAML not installed — still note that compose exists
        return {"active": True, "compose_file": str(compose_file), "services": []}
    except Exception:
        return {"active": True, "compose_file": str(compose_file), "services": []}
