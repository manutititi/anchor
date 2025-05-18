import os
import json
import base64
import urllib.request
from core.utils.colors import red, green, cyan, bold
from core.utils.path import resolve_path


def resolve_url_from_ref(ref, path):
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    anchor_path = os.path.join(anchor_dir, f"{ref}.json")
    if not os.path.isfile(anchor_path):
        print(red(f"❌ Referenced anchor '{ref}' not found"))
        return None

    with open(anchor_path) as f:
        data = json.load(f)

    base_url = data.get("endpoint", {}).get("base_url")
    if not base_url:
        print(red(f"❌ No base_url in anchor '{ref}'"))
        return None

    return base_url.rstrip("/") + "/" + path.lstrip("/")


def download_file(url, dest):
    try:
        with urllib.request.urlopen(url) as response:
            content = response.read()
            with open(dest, "wb") as f:
                f.write(content)
        return True
    except Exception as e:
        print(red(f"❌ Failed to download {url}: {e}"))
        return False


def write_file_from_content(dest, file_data):
    try:
        content = file_data.get("content", "")
        encoding = file_data.get("encoding", "plain")
        with open(dest, "wb") as f:
            if encoding == "base64":
                f.write(base64.b64decode(content))
            else:
                f.write(content.encode())
        return True
    except Exception as e:
        print(red(f"❌ Failed to write {dest}: {e}"))
        return False


def recreate_from_anchor(anchor_name, target_path):
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    anchor_file = os.path.join(anchor_dir, f"{anchor_name}.json")

    if not os.path.isfile(anchor_file):
        print(red(f"❌ Anchor not found: {anchor_file}"))
        return

    with open(anchor_file) as f:
        data = json.load(f)

    docker = data.get("docker", {})
    files = docker.get("files") or data.get("files")
    env_anchor = docker.get("env_anchor")

    if not files:
        print(red("❌ No files found to restore in anchor."))
        return

    os.makedirs(target_path, exist_ok=True)

    for rel_path, file_data in files.items():
        dest = os.path.join(target_path, rel_path)

        # Crear directorios vacíos (type: directory)
        if file_data.get("type") == "directory":
            try:
                os.makedirs(dest, exist_ok=True)
            except Exception as e:
                print(red(f"❌ Failed to create directory {dest}: {e}"))
            continue

        # Asegurar carpeta contenedora
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        if file_data.get("external"):
            url = None
            if file_data.get("ref") and file_data.get("path"):
                url = resolve_url_from_ref(file_data["ref"], file_data["path"])
            elif file_data.get("path", "").startswith("http://") or file_data.get("path", "").startswith("https://"):
                url = file_data["path"]

            if url:
                success = download_file(url, dest)
                if not success:
                    continue
            else:
                print(red(f"❌ No URL or ref for external file {rel_path}"))
                continue
        else:
            write_file_from_content(dest, file_data)

    if env_anchor:
        env_ref_path = os.path.abspath(os.path.join(target_path, ".anc_env"))
        try:
            with open(env_ref_path, "w") as f:
                f.write(env_anchor.strip() + "\n")
            print(green(f"🔗 Environment anchor reference created at {cyan(env_ref_path)}"))
        except Exception as e:
            print(red(f"❌ Failed to write .anc_env: {e}"))

    print(green(f"✅ Files restored from anchor '{bold(anchor_name)}' to {cyan(target_path)}"))


def run(args):
    anchor_name = args.anchor
    dest_path = resolve_path(args.path or ".", base_dir=os.getcwd())
    recreate_from_anchor(anchor_name, dest_path)
