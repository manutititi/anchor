import os
import json
from datetime import datetime, timezone

from core.utils.colors import green, cyan


def run(args):
    server_url = args.server or "http://localhost:17017"

    # Ruta del archivo info.json
    server_dir = os.path.expanduser(os.path.join(
        os.environ.get("ANCHOR_HOME", "~/.anchors"), "server"
    ))
    server_file = os.path.join(server_dir, "info.json")
    os.makedirs(server_dir, exist_ok=True)

    # Backup si ya existe
    if os.path.isfile(server_file):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_file = os.path.join(server_dir, f".oldserver_{timestamp}.json")
        with open(server_file, "rb") as fsrc, open(backup_file, "wb") as fdst:
            fdst.write(fsrc.read())

    # Guardar nueva configuración
    with open(server_file, "w") as f:
        json.dump({"url": server_url}, f, indent=2)

    os.chmod(server_file, 0o644)

    print(green(f"✅ Server URL set to: {cyan(server_url)}"))
