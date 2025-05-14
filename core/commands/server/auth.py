import json
import getpass
import requests
from pathlib import Path

from core.utils.colors import green, red, yellow, blue, dim

def run(args):
    # Ruta fija a ~/.anchors/server/info.json
    info_path = Path.home() / ".anchors" / "server" / "info.json"
    if not info_path.exists():
        print(red("ERROR: remote server not configured -> Use: anc server name <url>"))
        return

    with open(info_path) as f:
        server_info = json.load(f)

    server_url = server_info.get("url", "http://localhost:17017")

    username = args.username or input(" LDAP user: ")
    password = args.password or getpass.getpass("Password: ")

    try:
        response = requests.post(
            f"{server_url}/auth/login",
            json={"username": username, "password": password},
            timeout=5
        )
    except requests.exceptions.RequestException as e:
        print(red(f"ERROR: No se pudo conectar al servidor:\n{e}"))
        return

    if response.status_code != 200:
        print(red(f"ERROR: Autenticación fallida: {response.text}"))
        return

    data = response.json()
    token = data.get("access_token")
    groups = data.get("groups", [])
    user = data.get("username", username)

    if not token:
        print(red("ERROR: No se recibió token del servidor."))
        return

    server_info["token"] = token
    with open(info_path, "w") as f:
        json.dump(server_info, f, indent=2)

    print(green("Autenticación exitosa"))
    print(dim("-" * 40))
    print(f"{blue('Usuario:')}  {user}")
    print(f"{blue('Grupos:')}  {', '.join(groups) if groups else yellow('(ninguno)')}")
    print(f"{blue('Token:')}   Guardado en {dim(str(info_path))}")
    print(f"{blue('Servidor:')} {server_url}")
