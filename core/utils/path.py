import os

def resolve_path(raw_path: str, base_dir: str = None) -> str:
    """
    Expand routes like:
    - ~/algo → /home/user/algo
    - ./algo, ../algo → base_dir o cwd
    """
    if not raw_path:
        return ""

    if raw_path.startswith("~/"):
        return os.path.expanduser(raw_path)

    if raw_path.startswith("./") or raw_path.startswith("../"):
        base_dir = base_dir or os.environ.get("ANCHOR_HOME", os.getcwd())
        return os.path.abspath(os.path.join(base_dir, raw_path))

    return os.path.realpath(raw_path)
