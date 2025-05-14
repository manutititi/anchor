import json
import getpass
import requests
from pathlib import Path

from core.utils.colors import green, red, yellow, blue, dim

def run(args):
    # Fixed path to ~/.anchors/server/info.json
    info_path = Path.home() / ".anchors" / "server" / "info.json"
    if not info_path.exists():
        print(red("ERROR: Remote server not configured -> Use: anc server url <url>"))
        return

    with open(info_path) as f:
        server_info = json.load(f)

    server_url = server_info.get("url", "http://localhost:17017")

    username = args.username or input("LDAP user: ")
    password = args.password or getpass.getpass("Password: ")

    try:
        response = requests.post(
            f"{server_url}/auth/login",
            json={"username": username, "password": password},
            timeout=5
        )
    except requests.exceptions.RequestException as e:
        print(red(f"ERROR: Could not connect to server:\n{e}"))
        return

    if response.status_code != 200:
        print(red(f"ERROR: Authentication failed: {response.text}"))
        return

    data = response.json()
    token = data.get("access_token")
    groups = data.get("groups", [])
    user = data.get("username", username)

    if not token:
        print(red("ERROR: No token received from server."))
        return

    server_info["token"] = token
    with open(info_path, "w") as f:
        json.dump(server_info, f, indent=2)

    print(green("Authentication successful"))
    print(dim("-" * 40))
    print(f"{blue('User:')}    {user}")
    print(f"{blue('Groups:')}  {', '.join(groups) if groups else yellow('(none)')}")
    print(f"{blue('Token:')}   Saved to {dim(str(info_path))}")
    print(f"{blue('Server:')}  {server_url}")
