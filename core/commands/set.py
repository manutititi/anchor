import os
import json
import subprocess
from datetime import datetime, timezone
from collections import OrderedDict

from core.utils.colors import red, green, blue, yellow, cyan, bold
from core.utils.path import resolve_path
from core.utils.docker_meta import generate_docker_metadata


def now_iso(): return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def get_git_branches(path):
    try:
        return subprocess.check_output(["git", "-C", path, "branch", "--format=%(refname:short)"]).decode().splitlines()
    except Exception:
        return []

def detect_git_metadata(path):
    try:
        root = subprocess.check_output(["git", "-C", path, "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL).decode().strip()
        branch = subprocess.check_output(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        commit = subprocess.check_output(["git", "-C", path, "log", "-1", "--pretty=format:%H%n%an%n%ad%n%s"]).decode().split("\n")
        tags = subprocess.check_output(["git", "-C", path, "tag", "--points-at", "HEAD"]).decode().split()
        remotes_raw = subprocess.check_output(["git", "-C", path, "remote", "-v"]).decode().strip().split("\n")

        remotes = []
        seen = set()
        for line in remotes_raw:
            parts = line.split()
            if len(parts) >= 2:
                key = (parts[0], parts[1])
                if key not in seen:
                    seen.add(key)
                    remotes.append({ "name": parts[0], "url": parts[1] })

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
        return { "active": False }

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
        return { "active": True, "compose_file": compose_file, "services": [] }

def generate_local_metadata(path):
    meta = OrderedDict()
    meta["type"] = "local"
    meta["path"] = path
    meta["created_at"] = now_iso()

    git = detect_git_metadata(path)
    if git:
        meta["git"] = git

    docker = detect_docker_metadata(path)
    if docker.get("active"):
        meta["docker"] = docker

    return meta

def generate_url_metadata(name, base_url):
    return OrderedDict({
        "type": "url",
        "name": name,
        "meta": {
            "project": "",
            "env": "",
            "note": "",
            "created_by": os.environ.get("USER", "unknown"),
            "created_at": now_iso()
        },
        "endpoint": {
            "base_url": base_url,
            "version": "v1",
            "auth": {
                "enabled": False,
                "type": "bearer",
                "token_env": "API_TOKEN"
            },
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            "routes": []
        },
        "interfaces": {
            "docs": "",
            "dashboard": ""
        },
        "automation": {
            "test_enabled": True,
            "scan_enabled": False,
            "tools": []
        },
        "scripts": {
            "preload": [],
            "postload": []
        }
    })

def generate_env_metadata(name, env_vars=None):
    return OrderedDict({
        "type": "env",
        "name": name,
        "vars": env_vars or {
            "API_TOKEN": "",
            "DB_URL": "",
            "SECRET_KEY": "",
            "BASE_URL": "",
            "ENV": ""
        },
        "scripts": {
            "preload": [],
            "postload": []
        },
        "meta": {
            "created_by": os.environ.get("USER", "unknown"),
            "created_at": now_iso(),
            "description": "",
            "tags": [],
            "shared": False,
            "encrypted": False
        }
    })

def parse_env_file(env_path):
    env_vars = {}
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip().strip('"').strip("'")
    return env_vars




def generate_ldap_metadata(name, host, base_dn, bind_dn, bind_password):
    return OrderedDict({
        "type": "ldap",
        "name": name,
        "host": host,
        "base_dn": base_dn,
        "bind_dn": bind_dn,
        "bind_password": bind_password,
        "user_dn": f"ou=users,{base_dn}",
        "group_dn": f"ou=groups,{base_dn}",
        "user_filter": "(uid={username})",
        "group_filter": "(member={user_dn})",
        "attributes": {
            "uid": "username",
            "cn": "fullname",
            "sn": "surname",
            "memberOf": "groups"
        },
        "tls": host.startswith("ldaps://"),
        "meta": {
            "created_by": os.environ.get("USER", "unknown"),
            "created_at": now_iso(),
            "description": "LDAP anchor",
            "tags": []
        }
    })



# === MAIN ===
def run(args):
    if args.server is not None:
        return handle_server(args)

    os.makedirs(args.anchor_dir, exist_ok=True)

    # --- ENV mode ---
    if args.env:
        name = args.name
        if not name:
            print(red("❌ Usage: anc set --env <name> [.env_file]"))
            return

        if name.endswith(".json"):
            name = name[:-5]

        filename = f"{name}.json"
        meta_path = os.path.join(args.anchor_dir, filename)

        if os.path.exists(meta_path):
            print(yellow(f"⚠️  Environment already exists: {meta_path}"))
            print(red("❌ Use 'anc meta' to modify it."))
            return

        env_vars = {}
        if args.base_url:
            env_file = os.path.abspath(args.base_url)
            if not os.path.isfile(env_file):
                print(red(f"❌ File '{env_file}' not found."))
                return
            env_vars = parse_env_file(env_file)

        data = generate_env_metadata(name, env_vars)

        with open(meta_path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=False)

        print(green(f"✅ Environment '{bold(name)}' created at {cyan(meta_path)}"))

        with open(".anc_env", "w") as f:
            f.write(name)
        print(blue(f"📎 Linked current directory to env '{bold(name)}' via .anc_env"))
        return

    # --- URL mode ---
    if args.url:
        name = args.name
        base_url = args.base_url

        if not name or not base_url:
            print(red("❌ Usage: anc set --url <name> <base_url>"))
            return

        if name.endswith(".json"):
            name = name[:-5]

        filename = f"{name}.json"
        meta_path = os.path.join(args.anchor_dir, filename)

        if os.path.exists(meta_path):
            print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
            print(red("❌ Use 'anc meta' or 'anc add-route' to modify it."))
            return

        meta = generate_url_metadata(name, base_url)
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, sort_keys=False)

        print(green(f"✅ Anchor '{bold(name)}' created as type '{cyan('url')}'"))
        print(blue(f"🌐 Base URL: {base_url}"))
        return
    


        # --- Docker mode ---
    if args.docker:
        name = args.name
        if not name:
            print(red("❌ Usage: anc set --docker <name> [path]"))
            return

        if name.endswith(".json"):
            name = name[:-5]

        base_path = resolve_path(args.base_url or ".")
        filename = f"{name}.json"
        meta_path = os.path.join(args.anchor_dir, filename)

        if os.path.exists(meta_path):
            print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
            confirm = input("Overwrite? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                print(red("❌ Aborted. Anchor not overwritten."))
                return

        meta = OrderedDict()
        meta["type"] = "docker"
        meta["name"] = name
        meta["path"] = base_path
        meta["created_at"] = now_iso()

        git = detect_git_metadata(base_path)
        if git:
            meta["git"] = git

        docker = generate_docker_metadata(base_path)

        # Detect.env 
        env_path = os.path.join(base_path, ".env")
        if os.path.isfile(env_path):
            print(yellow(".env file detected. What would you like to do?"))
            print("  1. Include the .env content in the anchor")
            print("  2. Do NOT include it")
            print("  3. Create a separate env anchor and link to it")
            choice = input("Choose [1/2/3]: ").strip()

            if choice == "1":
                from core.utils.docker_meta import read_file_content, should_encode_file
                content = read_file_content(env_path, encode=should_encode_file(env_path))
                if content:
                    docker.setdefault("files", {})[".env"] = content

            elif choice == "3":
                default_env_name = f"{name}-env"
                env_name = input(f"Enter a name for the environment anchor [{default_env_name}]: ").strip() or default_env_name
                env_vars = parse_env_file(env_path)
                env_anchor_path = os.path.join(args.anchor_dir, f"{env_name}.json")
                env_meta = generate_env_metadata(env_name, env_vars)
                with open(env_anchor_path, "w") as f:
                    json.dump(env_meta, f, indent=2)
                print(green(f"✅ Environment anchor created as '{env_anchor_path}'"))
                docker["env_anchor"] = env_name

        #  Detect big files
        big_files = [k for k, v in docker.get("files", {}).items() if v.get("external") and not v.get("path", "").startswith("http")]
        if big_files:
            print(yellow("📦 Large external files detected:"))
            for bf in big_files:
                print(f"  • {bf}")

            confirm = input("Do you want to upload them now? [y/N] ").strip().lower()
            if confirm in ("y", "yes"):
                upload_url = input("Enter base upload URL (e.g. http://localhost:17017/files): ").strip().rstrip("/")
                for relpath in big_files:
                    absf = os.path.join(base_path, relpath)
                    print(f"⬆️  Uploading {relpath} ...", end=" ", flush=True)
                    try:
                        import requests
                        with open(absf, "rb") as f:
                            response = requests.post(upload_url + "/upload", files={"file": (os.path.basename(relpath), f)})
                        if response.status_code == 200:
                            rj = response.json()
                            docker["files"][relpath]["path"] = upload_url + "/" + os.path.basename(relpath)
                            docker["files"][relpath]["ref"] = None
                            print(green("done"))
                        else:
                            print(red(f"❌ failed ({response.status_code})"))
                    except Exception as e:
                        print(red(f"❌ {e}"))

        if docker.get("active"):
            meta["docker"] = docker
        else:
            print(red(f"❌ No valid docker-compose.yml found in: {base_path}"))
            return

        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, sort_keys=False)

        print(cyan(f"⚓ Docker anchor '{bold(name)}' created at: {green(meta_path)}"))
        print(blue("🐳 Docker Compose detected and embedded"))
        print(f"  {cyan('Services:')}")
        for s in docker.get("services", []):
            print(f"    - {s.get('name')} ({s.get('image')})")
        print(f"  {cyan('Files captured:')} {len(docker.get('files', {}))}")
        return

    

    # --- LDAP mode ---
    if args.ldap:
        name = args.name
        if not name:
            print(red("❌ Usage: anc set --ldap <name>"))
            return

        if name.endswith(".json"):
            name = name[:-5]

        filename = f"{name}.json"
        meta_path = os.path.join(args.anchor_dir, filename)

        if os.path.exists(meta_path):
            print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
            confirm = input("Overwrite? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                print(red("❌ Aborted. Anchor not overwritten."))
                return

        # Si no hay args explícitos, preguntar interactivo
        def prompt(prompt_text, default):
            val = input(f"{prompt_text} [{default}]: ").strip()
            return val or default

        host = args.base_url or prompt("LDAP host URL", "ldap://localhost:8389")
        base_dn = args.base_dn or prompt("Base DN", "dc=anchor,dc=local")
        bind_dn = args.bind_dn or prompt("Bind DN", f"cn=admin,{base_dn}")
        bind_password = args.bind_password or prompt("Bind password", "admin")

        meta = generate_ldap_metadata(name, host, base_dn, bind_dn, bind_password)

        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, sort_keys=False)

        print(green(f"✅ LDAP anchor '{bold(name)}' created"))
        print(blue(f"🔗 Host: {cyan(host)}"))
        print(f"  {cyan('Base DN:')} {base_dn}")
        print(f"  {cyan('Bind DN:')} {bind_dn}")
        return








    # --- Default (local path) ---
    input_val = args.name
    if not input_val or input_val.startswith("/") or input_val.startswith(".") or os.path.isdir(input_val):
        abs_path = resolve_path(input_val)
        path = abs_path
        name = os.path.basename(abs_path)
    else:
        name = input_val
        abs_path = os.getcwd()
        path = abs_path

    if args.rel and abs_path.startswith(os.path.expanduser("~")):
        path = path.replace(os.path.expanduser("~"), "~", 1)

    if name.endswith(".json"):
        name = name[:-5]

    filename = f"{name}.json"
    meta_path = os.path.join(args.anchor_dir, filename)

    if os.path.exists(meta_path):
        print(yellow(f"⚠️  Anchor already exists: {meta_path}"))
        confirm = input("Overwrite? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print(red("❌ Aborted. Anchor not overwritten."))
            return

    meta = generate_local_metadata(path)
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=False)

    print(cyan(f"⚓ Anchor '{bold(name)}'") + cyan(" set to: ") + green(path))

    if "git" in meta:
        g = meta["git"]
        print(blue("🔍 Git repository detected:"))
        print(f"  {cyan('Branch:')} {g['branch']}")
        print(f"  {cyan('Root:')} {g['root']}")
        print(f"  {cyan('Last commit:')} {g['commit']['message']}")
        if g.get("is_dirty"):
            print(red("  ⚠️ Working directory has uncommitted changes"))

    if "docker" in meta and meta["docker"].get("active"):
        print(blue("🐳 Docker Compose detected:"))
        print(f"  {cyan('Services:')}")
        for s in meta["docker"].get("services", []):
            print(f"    - {s.get('name')}")





    

# === SERVER ===
def handle_server(args):
    server_url = args.server or "http://localhost:17017"

    server_dir = os.path.expanduser(os.path.join(os.environ.get("ANCHOR_HOME", "~/.anchors"), "server"))
    server_file = os.path.join(server_dir, "info.json")
    os.makedirs(server_dir, exist_ok=True)

    if os.path.isfile(server_file):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_file = os.path.join(server_dir, f".oldserver_{timestamp}.json")
        with open(server_file, "rb") as fsrc, open(backup_file, "wb") as fdst:
            fdst.write(fsrc.read())

    with open(server_file, "w") as f:
        json.dump({ "url": server_url }, f, indent=2)

    os.chmod(server_file, 0o644)

    print(green(f"✅ Server URL set to: {cyan(server_url)}"))


