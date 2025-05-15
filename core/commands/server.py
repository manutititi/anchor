import os
import json
import getpass
import requests
from pathlib import Path

INFO_PATH = Path(__file__).resolve().parent.parent / "server" / "info.json"
INFO_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_server_url():
    if INFO_PATH.exists():
        with open(INFO_PATH) as f:
            return json.load(f).get("url", "http://localhost:17017")
    return "http://localhost:17017"


def save_token(token: str):
    if INFO_PATH.exists():
        with open(INFO_PATH) as f:
            data = json.load(f)
    else:
        data = {}

    data["token"] = token
    with open(INFO_PATH, "w") as f:
        json.dump(data, f, indent=2)


def handle_auth(args):
    username = args.username or input("👤 Username: ")
    password = args.password or getpass.getpass("🔐 Password: ")

    url = get_server_url().rstrip("/") + "/auth/login"
    payload = {"username": username, "password": password}

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Error connecting to server: {e}")
        return

    data = response.json()
    token = data.get("access_token")
    if token:
        save_token(token)
        print(f"✅ Authenticated as {data.get('username')} | groups: {data.get('groups')}\n🔐 Token saved in info.json")
        if args.json:
            print(json.dumps(data, indent=2))
    else:
        print("❌ Authentication failed. No token returned.")


def run(args):
    if args.action == "auth":
        handle_auth(args)
    else:
        print(f"❌ Unknown server action: {args.action}")
