import os
import json
from core.utils.colors import red, green, cyan, bold
from core.utils.path import resolve_path


def regenerate_docker_environment(anchor_file, target_path):
    """
    Reconstruye los archivos del entorno Docker desde el JSON del anchor.
    """
    if not os.path.isfile(anchor_file):
        print(red(f"❌ Anchor not found: {anchor_file}"))
        return False

    with open(anchor_file) as f:
        data = json.load(f)

    if data.get("type") != "docker":
        print(red("❌ Anchor is not of type 'docker'"))
        return False

    docker_data = data.get("docker", {})
    files = docker_data.get("files", {})
    os.makedirs(target_path, exist_ok=True)

    for rel_path, file_data in files.items():
        dest = os.path.join(target_path, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            content = file_data.get("content", "")
            encoding = file_data.get("encoding", "plain")
            with open(dest, "wb") as f:
                if encoding == "base64":
                    import base64
                    f.write(base64.b64decode(content))
                else:
                    f.write(content.encode())
        except Exception as e:
            print(red(f"❌ Failed to write {rel_path}: {e}"))

    compose_file = docker_data.get("compose_file", "docker-compose.yml")
    print(green(f"✅ Environment restored at {bold(target_path)} (compose: {compose_file})"))
    return True


def run(args):
    if args.restore:
        anchor_name = args.restore[0] if len(args.restore) > 0 else None
        path_arg = args.restore[1] if len(args.restore) > 1 else None

        if not anchor_name:
            print(red("❌ Usage: anc docker -r <anchor> [path]"))
            return

        anchor_dir = os.environ.get("ANCHOR_DIR", "data")
        anchor_file = os.path.join(anchor_dir, f"{anchor_name}.json")
        dest_path = resolve_path(path_arg or ".")

        regenerate_docker_environment(anchor_file, dest_path)
        return