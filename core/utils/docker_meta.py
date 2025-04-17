import os
import base64
import yaml
import hashlib

def read_file_content(path, encode=False):
    try:
        with open(path, "rb") as f:
            content = f.read()
        if encode:
            return {
                "content": base64.b64encode(content).decode(),
                "encoding": "base64"
            }
        else:
            try:
                return {
                    "content": content.decode(),
                    "encoding": "plain"
                }
            except UnicodeDecodeError:
                return {
                    "content": base64.b64encode(content).decode(),
                    "encoding": "base64"
                }
    except Exception:
        return None

def rel(path, base):
    try:
        return os.path.relpath(path, base)
    except Exception:
        return path

def should_encode_file(path):
    extensions_base64 = ['.crt', '.key', '.pem', '.pfx', '.jks']
    _, ext = os.path.splitext(path)
    return ext.lower() in extensions_base64

def compute_sha256(path):
    try:
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return None

def find_related_files(compose_data, root_path, size_limit=1_000_000):
    files = {}

    def resolve(p):
        if p.startswith("./") or p.startswith("../") or not os.path.isabs(p):
            return os.path.normpath(os.path.join(root_path, p))
        return p

    for service in compose_data.get("services", {}).values():
        for volume in service.get("volumes", []):
            host_path = volume.split(":")[0]
            full_path = resolve(host_path)
            if os.path.isdir(full_path):
                for dirpath, _, filenames in os.walk(full_path):
                    for f in filenames:
                        absf = os.path.join(dirpath, f)
                        relf = os.path.relpath(absf, root_path)
                        size = os.path.getsize(absf)
                        if size > size_limit:
                            files[relf] = {
                                "external": True,
                                "size": size,
                                "sha256": compute_sha256(absf),
                                "ref": None,
                                "path": f"/files/{os.path.basename(absf)}"
                            }
                        else:
                            content = read_file_content(absf, encode=should_encode_file(absf))
                            if content:
                                files[relf] = content
            elif os.path.isfile(full_path):
                relf = os.path.relpath(full_path, root_path)
                size = os.path.getsize(full_path)
                if size > size_limit:
                    files[relf] = {
                        "external": True,
                        "size": size,
                        "sha256": compute_sha256(full_path),
                        "ref": None,
                        "path": f"/files/{os.path.basename(full_path)}"
                    }
                else:
                    content = read_file_content(full_path, encode=should_encode_file(full_path))
                    if content:
                        files[relf] = content

    return files

def find_contextual_files(root_path, size_limit=1_000_000):
    important = ["Dockerfile", "requirements.txt", "server.py", "main.py", "app.py"]
    files = {}

    for fname in important:
        full_path = os.path.join(root_path, fname)
        if os.path.isfile(full_path):
            size = os.path.getsize(full_path)
            if size > size_limit:
                files[fname] = {
                    "external": True,
                    "size": size,
                    "sha256": compute_sha256(full_path),
                    "ref": None,
                    "path": f"/files/{fname}"
                }
            else:
                content = read_file_content(full_path, encode=should_encode_file(full_path))
                if content:
                    files[fname] = content

    return files

def generate_docker_metadata(path):
    compose_path = os.path.join(path, "docker-compose.yml")
    if not os.path.isfile(compose_path):
        return { "active": False }

    try:
        with open(compose_path, "r") as f:
            raw = f.read()
            data = yaml.safe_load(raw)

        services = []
        for name, config in data.get("services", {}).items():
            services.append({
                "name": name,
                "image": config.get("image", ""),
                "build": config.get("build", ""),
                "ports": config.get("ports", []),
                "volumes": config.get("volumes", []),
                "env_file": config.get("env_file", []),
                "depends_on": config.get("depends_on", []),
            })

        files = find_related_files(data, path)
        files.update(find_contextual_files(path))

        compose_rel = rel(compose_path, path)
        files[compose_rel] = {
            "content": raw,
            "encoding": "plain"
        }

        return {
            "active": True,
            "compose_file": compose_rel,
            "services": services,
            "files": files
        }

    except Exception as e:
        return {
            "active": False,
            "error": str(e)
        }
