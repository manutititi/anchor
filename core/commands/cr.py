import os
import json
import base64
from datetime import datetime
from core.utils.colors import red, green, bold, cyan
from core.utils.path import resolve_path, as_relative_to_home


def get_file_perm(path):
    try:
        return format(os.stat(path).st_mode & 0o7777, "04o")
    except Exception as e:
        print(red(f"❌ Error getting permissions for {path}: {e}"))
        return "0000"




def encode_file(filepath):
    try:
        with open(filepath, "rb") as f:
            raw = f.read()
            try:
                raw.decode()
                return raw.decode(), "plain"
            except UnicodeDecodeError:
                return base64.b64encode(raw).decode(), "base64"
    except Exception as e:
        print(red(f"❌ Failed to read {filepath}: {e}"))
        return None, None


def should_become(path):
    return path.startswith("/etc") or path.startswith("/usr") or path.startswith("/var") or path.startswith("/opt") or path.startswith("/root")


def parse_paths_modes_and_flags(raw_args, default_mode="replace"):
    result = []
    current_path = None
    current_mode = default_mode
    current_blank = False
    i = 0

    while i < len(raw_args):
        token = raw_args[i]

        if token == "--mode":
            i += 1
            if i >= len(raw_args):
                raise ValueError("❌ Missing value after --mode")
            current_mode = raw_args[i]

        elif token == "--blank":
            current_blank = True

        else:
            if current_path:
                result.append((current_path, current_mode, current_blank))
                current_mode = default_mode
                current_blank = False
            current_path = token

        i += 1

    if current_path:
        result.append((current_path, current_mode, current_blank))

    return result


def build_files_dict_from_paths(triplets, base_root=None):
    files_dict = {}

    for upath_raw, mode, blank in triplets:
        resolved = resolve_path(upath_raw)
        if base_root:
            upath = os.path.relpath(resolved, start=base_root)
        else:
            upath = as_relative_to_home(upath_raw)

        if not os.path.exists(resolved):
            print(red(f"❌ Not found: {upath_raw}"))
            return {}

        if os.path.isfile(resolved):
            key = os.path.normpath(upath)
            content, encoding = encode_file(resolved)
            if encoding is not None:
                entry = {
                    "mode": mode
                }
                if mode == "regex":
                    entry["submode"] = "replace"
                entry.update({
                    "become": should_become(key),
                    "encoding": encoding,
                    "regex": "" if mode == "regex" else None,
                    "content": "" if blank or mode == "regex" else content
                })
                entry["perm"] = get_file_perm(resolved)

                if mode != "regex":
                    entry.pop("regex", None)
                files_dict[key] = entry

        elif os.path.isdir(resolved):
            for root, dirs, files in os.walk(resolved):
                rel_root = os.path.relpath(root, base_root or resolved)
                key_root = os.path.normpath(os.path.join(upath.rstrip("/"), rel_root)).rstrip("/") + "/"

                # Añadir solo si es un directorio vacío
                if not files and not dirs:
                    files_dict[key_root] = {
                        "type": "directory",
                        "mode": "ensure",
                        "become": should_become(key_root),
                        "perm": get_file_perm(root)
                    }

                for name in files:
                    full_path = os.path.join(root, name)
                    rel_inside = os.path.relpath(full_path, base_root or resolved)
                    key = os.path.normpath(os.path.join(upath.rstrip("/"), rel_inside))
                    content, encoding = encode_file(full_path)
                    if encoding is not None:
                        entry = {
                            "mode": mode
                        }
                        if mode == "regex":
                            entry["submode"] = "replace"
                        entry.update({
                            "become": should_become(key),
                            "encoding": encoding,
                            "regex": "" if mode == "regex" else None,
                            "content": "" if blank or mode == "regex" else content
                        })
                        entry["perm"] = get_file_perm(full_path)
                        if mode != "regex":
                            entry.pop("regex", None)
                        files_dict[key] = entry

    return files_dict


def handle_cr(args):
    """
    anc cr <name> path [--mode <mode>] [--blank] path ...
    """
    anchor_name = args.name

    try:
        parsed_inputs = parse_paths_modes_and_flags(args.paths or [], default_mode=args.mode or "replace")
    except ValueError as e:
        print(red(str(e)))
        return

    if not parsed_inputs:
        # Caso: anc cr name (sin rutas explícitas)
        cwd = os.getcwd()
        print(cyan(f"📂 No path provided, using current directory recursively: {cwd}"))
        parsed_inputs = [(".", args.mode or "replace", False)]
        show_dot_as_root = True
    else:
        show_dot_as_root = False

    valid_modes = {"replace", "append", "prepend", "regex"}

    for path, mode, _ in parsed_inputs:
        if mode not in valid_modes:
            print(red(f"❌ Invalid mode '{mode}' for path '{path}'"))
            return
        if not os.path.exists(resolve_path(path)):
            print(red(f"❌ Path not found: {path}"))
            return

    if any(mode == "regex" for _, mode, _ in parsed_inputs):
        print(cyan("📌 Hint: don't forget to manually define 'regex' patterns in the anchor JSON."))

    files_dict = build_files_dict_from_paths(parsed_inputs)
    paths = [as_relative_to_home(p) for p, _, _ in parsed_inputs]

    anchor_data = {
    "type": "files",
    "name": anchor_name,
    "path": "." if show_dot_as_root else (paths if len(paths) > 1 else paths[0]),
    "files": files_dict,
    "scripts": {
        "_comment": "You can use simple strings or objects like {'run': 'command', 'scope': 'path', 'become': 'true'}",
        "preload": [],
        "postload": []
    },
    "created_by": os.getenv("USER") or "unknown",
    "last_updated": datetime.now().isoformat(),
    "updated_by": os.getenv("USER") or "unknown"
}


    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    os.makedirs(anchor_dir, exist_ok=True)
    output_file = os.path.join(anchor_dir, f"{anchor_name}.json")

    with open(output_file, "w") as f:
        json.dump(anchor_data, f, indent=2)

    print(green(f"✅ Anchor {bold(anchor_name)} created at {bold(output_file)}"))
