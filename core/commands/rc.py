import os
import json
import base64
from core.utils.colors import red, green, cyan, bold
from core.utils.path import resolve_path


def recreate_from_anchor(anchor_name, target_path):
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    anchor_file = os.path.join(anchor_dir, f"{anchor_name}.json")

    if not os.path.isfile(anchor_file):
        print(red(f"❌ Anchor not found: {anchor_file}"))
        return

    with open(anchor_file) as f:
        data = json.load(f)

    files = data.get("docker", {}).get("files") or data.get("files")
    if not files:
        print(red("❌ No files found to restore in anchor."))
        return

    os.makedirs(target_path, exist_ok=True)

    for rel_path, file_data in files.items():
        dest = os.path.join(target_path, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            content = file_data.get("content", "")
            encoding = file_data.get("encoding", "plain")
            with open(dest, "wb") as f:
                if encoding == "base64":
                    f.write(base64.b64decode(content))
                else:
                    f.write(content.encode())
        except Exception as e:
            print(red(f"❌ Failed to write {rel_path}: {e}"))

    print(green(f"✅ Files restored from anchor '{bold(anchor_name)}' to {cyan(target_path)}"))


def run(args):
    anchor_name = args.anchor
    dest_path = resolve_path(args.path or ".", base_dir=os.getcwd())
    recreate_from_anchor(anchor_name, dest_path)
