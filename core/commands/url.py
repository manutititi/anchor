import os
import json
import subprocess
from pathlib import Path
from collections import OrderedDict


def color(text, code): return f"\033[{code}m{text}\033[0m"
def green(t): return color(t, "0;32")
def red(t): return color(t, "0;31")
def yellow(t): return color(t, "0;33")
def cyan(t): return color(t, "1;36")
def bold(t): return color(t, "1")
def blue(t): return color(t, "1;34")


def run(args):
    if args.add_route:
        return handle_add_route(args)
    if args.test:
        return handle_test_routes(args)
    if args.del_route:
        return handle_delete_route(args)
    if args.call:
        return handle_call(args)


def handle_add_route(args):
    anchor_name = args.anchor
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")

    if not anchor_name:
        print(yellow("Usage: anc url -a <anchor> [METHOD] [PATH] [key=val ...] [status]"))
        return

    if not anchor_name.endswith(".json"):
        anchor_name += ".json"

    file_path = Path(anchor_dir) / anchor_name
    if not file_path.exists():
        print(red(f"❌ Anchor '{anchor_name}' not found at {file_path}"))
        return

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(red(f"❌ Failed to load anchor: {e}"))
        return

    if data.get("type") != "url":
        print(red(f"❌ Anchor '{anchor_name}' is not of type 'url'."))
        return

    method = args.method
    path = args.route_path
    kvpairs = args.kv

    if not method:
        method = input("🔧 HTTP method (GET, POST, etc): ").strip().upper()
    if not path:
        path = input("🛣️  Route path (e.g. /users): ").strip()
    if not kvpairs:
        raw = input("🧩 Params key=value (space-separated, optional): ").strip()
        status_input = input("✅ Expected status code (default: 200): ").strip()
        kvpairs = raw.split()
        if status_input:
            kvpairs.append(status_input)

    params = {}
    expected_status = 200
    for kv in kvpairs:
        if "=" in kv:
            k, v = kv.split("=", 1)
            params[k] = v
        elif kv.isdigit():
            expected_status = int(kv)

    new_route = OrderedDict({
        "name": f"{method} {path}",
        "method": method,
        "path": path,
        "params": params,
        "expect": {"status": expected_status}
    })

    data.setdefault("endpoint", {}).setdefault("routes", []).append(new_route)

    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        print(green(f"✅ Route added to '{bold(anchor_name)}': {cyan(method)} {path} → expect {expected_status}"))
    except Exception as e:
        print(red(f"❌ Failed to write anchor: {e}"))


def handle_test_routes(args):
    anchor_name = args.anchor
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")

    if not anchor_name:
        print("Usage: anc url --test <anchor>")
        return

    if not anchor_name.endswith(".json"):
        anchor_name += ".json"

    file_path = Path(anchor_dir) / anchor_name
    if not file_path.exists():
        print(red(f"❌ Anchor '{anchor_name}' not found at {file_path}"))
        return

    try:
        with open(file_path) as f:
            data = json.load(f)
    except Exception as e:
        print(red(f"❌ Failed to load anchor: {e}"))
        return

    if data.get("type") != "url":
        print(red(f"❌ Anchor '{anchor_name}' is not of type 'url'."))
        return

    base_url = data.get("endpoint", {}).get("base_url", "")
    auth_enabled = data.get("endpoint", {}).get("auth", {}).get("enabled", False)
    token_env = data.get("endpoint", {}).get("auth", {}).get("token_env", "")
    routes = data.get("endpoint", {}).get("routes", [])

    if not routes:
        print(yellow(f"⚠️ No test routes defined for '{anchor_name}'."))
        return

    print(cyan(f"🔍 Testing {len(routes)} route(s) for '{anchor_name}'..."))

    for route in routes:
        method = route.get("method", "GET")
        path_template = route.get("path", "")
        expect = route.get("expect", {}).get("status", 200)
        params = route.get("params", {})

        placeholders = [p.strip("{}") for p in path_template.split("/") if p.startswith("{") and p.endswith("}")]
        test_paths = []

        if not placeholders:
            test_paths = [path_template]
        else:
            placeholder = placeholders[0]
            variants = [v for k, v in params.items() if k.startswith(placeholder)]
            if not variants:
                variants = [params.get(placeholder, "test")]
            test_paths = [path_template.replace(f"{{{placeholder}}}", str(val)) for val in variants]

        for path in test_paths:
            url = f"{base_url}{path}"
            cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", method, url]

            if auth_enabled and token_env in os.environ:
                token = os.environ[token_env]
                cmd += ["-H", f"Authorization: Bearer {token}"]

            try:
                result = subprocess.check_output(cmd).decode().strip()
                if result == str(expect):
                    print(green(f"✅ {method} {path} → {result}"))
                else:
                    print(red(f"❌ {method} {path} → {result} (expected {expect})"))
            except Exception as e:
                print(red(f"❌ {method} {path} → failed ({e})"))


def handle_delete_route(args):
    anchor_name = args.anchor
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")

    if not anchor_name:
        print("Usage: anc url -d <anchor>")
        return

    if not anchor_name.endswith(".json"):
        anchor_name += ".json"

    file_path = Path(anchor_dir) / anchor_name
    if not file_path.exists():
        print(red(f"❌ Anchor '{anchor_name}' not found at {file_path}"))
        return

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(red(f"❌ Failed to load anchor: {e}"))
        return

    if data.get("type") != "url":
        print(red(f"❌ Anchor '{anchor_name}' is not of type 'url'."))
        return

    routes = data.get("endpoint", {}).get("routes", [])
    if not routes:
        print(yellow(f"⚠️ No routes found in '{anchor_name}'"))
        return

    print(cyan(f"🧭 Routes in '{anchor_name}':"))
    for i, r in enumerate(routes):
        print(f"  {i + 1}. {r.get('method', '')} {r.get('path', '')}")

    choice = input("\n🗑️  Enter the number of the route to delete (or 0 to cancel): ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(routes):
        print(yellow("❌ Cancelled."))
        return

    idx = int(choice) - 1
    deleted = routes.pop(idx)

    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        print(green(f"✅ Deleted route: {deleted.get('method')} {deleted.get('path')}"))
    except Exception as e:
        print(red(f"❌ Failed to save anchor: {e}"))




import mimetypes


def handle_call(args):
    anchor_name = args.call[0]
    method = args.call[1].upper() if len(args.call) > 1 else "GET"
    route_path = args.call[2] if len(args.call) >= 3 and not args.call[2].endswith(".json") else ""
    payloads = args.call[3:] if len(args.call) >= 4 else []

    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    anchor_file = Path(anchor_dir) / f"{anchor_name}.json"

    if not anchor_file.exists():
        print(red(f"❌ Anchor '{anchor_name}' not found at {anchor_file}"))
        return

    with open(anchor_file) as f:
        data = json.load(f)

    if data.get("type") != "url":
        print(red(f"❌ Anchor '{anchor_name}' is not of type 'url'"))
        return

    base_url = data.get("endpoint", {}).get("base_url", "")
    auth = data.get("endpoint", {}).get("auth", {})
    headers = data.get("endpoint", {}).get("headers", {})

    full_url = base_url.rstrip("/")
    if route_path:
        full_url = f"{full_url}/{route_path.lstrip('/')}"

    cmd = ["curl", "-s", "-X", method, full_url]

    # Headers generales
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]

    # Token si aplica
    if auth.get("enabled") and auth.get("token_env") in os.environ:
        token = os.environ[auth["token_env"]]
        cmd += ["-H", f"Authorization: Bearer {token}"]

    # Envío de datos: JSON por defecto, -F para archivos
    if method in ("POST", "PUT", "PATCH") and payloads:
        if hasattr(args, "F") and args.F:
            for file in payloads:
                cmd += ["-F", f"file=@{file}"]
        else:
            if len(payloads) == 1 and payloads[0].endswith(".json"):
                try:
                    with open(payloads[0]) as f:
                        json_data = f.read()
                    cmd += ["-H", "Content-Type: application/json", "-d", json_data]
                except Exception as e:
                    print(red(f"❌ Error reading JSON file: {e}"))
                    return
            else:
                # Si se pasa contenido directamente
                joined = " ".join(payloads)
                cmd += ["-H", "Content-Type: application/json", "-d", joined]

    print(blue(f"🌐 {method} {full_url}"))
    subprocess.run(cmd)
