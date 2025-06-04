import os
import sys
import json
import base64
import urllib.request
import re
import hashlib
import subprocess
from core.utils.colors import red, green, cyan, bold
from core.utils.path import resolve_path

skipped_files = []
changed_files = []

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
        changed_files.append(dest)
        return True
    except Exception as e:
        print(red(f"❌ Failed to download {url}: {e}"))
        return False


def write_file_from_content(dest, file_data):
    try:
        content = file_data.get("content", "")
        encoding = file_data.get("encoding", "plain")
        mode = file_data.get("mode", "replace")
        decoded = base64.b64decode(content) if encoding == "base64" else content.encode()

        if mode == "replace":
            if os.path.exists(dest):
                with open(dest, "rb") as f:
                    current_md5 = hashlib.md5(f.read()).digest()
                new_md5 = hashlib.md5(decoded).digest()

                if current_md5 == new_md5:
                    skipped_files.append(dest)
                    return True

            with open(dest, "wb") as f:
                f.write(decoded)
            changed_files.append(dest)

        elif mode == "append":
            with open(dest, "ab") as f:
                f.write(decoded)
            changed_files.append(dest)

        elif mode == "prepend":
            if os.path.exists(dest):
                with open(dest, "rb") as f:
                    existing = f.read()
            else:
                existing = b""
            with open(dest, "wb") as f:
                f.write(decoded + existing)
            changed_files.append(dest)

        elif mode == "regex":
            regex = file_data.get("regex", "")
            submode = file_data.get("submode", "replace")
            new_content = decoded.decode()

            if not os.path.exists(dest):
                print(red(f"❌ Cannot apply regex: file does not exist: {dest}"))
                return False

            with open(dest, "r", encoding="utf-8") as f:
                original = f.read()

            if submode == "replace":
                try:
                    result = re.sub(regex, new_content, original, flags=re.MULTILINE)
                    with open(dest, "w", encoding="utf-8") as f:
                        f.write(result)
                    changed_files.append(dest)
                except Exception as e:
                    print(red(f"❌ Regex error in {dest}: {e}"))
                    return False
            else:
                print(red(f"❌ Unsupported regex submode: {submode}"))
                return False

        else:
            print(red(f"❌ Unknown mode '{mode}' for {dest}"))
            return False

        return True

    except Exception as e:
        print(red(f"❌ Failed to write {dest}: {e}"))
        return False


def run_script_block(blocks, when="preload"):
    if not blocks:
        return
    print(f"\n🛠️  Executing {when} scripts...")
    for script in blocks:
        if isinstance(script, str):
            cmd = script
            scope = "."
        else:
            cmd = script.get("run")
            scope = script.get("scope", ".")
        
        scope = os.path.expanduser(scope)  # Expande ~ a /home/user

        print(f" → cd {scope} && {cmd}")
        try:
            subprocess.run(cmd, cwd=scope, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(red(f"❌ Script failed in {scope}: {e}"))





def escalate_if_needed(files, target_path, anchor_name):
    if os.geteuid() == 0:
        return  # Ya somos root

    privileged_paths = []
    for rel_path in files:
        is_absolute = rel_path.startswith("~") or rel_path.startswith("/")
        dest = os.path.expanduser(rel_path) if is_absolute else os.path.join(target_path, rel_path)
        if dest.startswith("/etc") or dest.startswith("/usr") or dest.startswith("/opt") or dest.startswith("/root") or dest.startswith("/dert"):
            privileged_paths.append(dest)

    if privileged_paths:
        print(red("\n⚠️  Some files are located in protected system paths and require root permissions:\n"))
        for path in privileged_paths:
            print("   " + path)
        print()
        print(cyan("❓ Do you want to re-run with sudo using the Anchor venv?"))
        choice = input(cyan("   [y/N]: ")).strip().lower()
        if choice != "y":
            print(red("❌ Aborted."))
            sys.exit(1)

        # Reinvocar el comando como sudo + python del venv con rutas absolutas
        anchor_root = os.path.expanduser("~/.anchors")
        venv_python = os.path.join(anchor_root, "venv", "bin", "python3")
        main_py = os.path.join(anchor_root, "core", "main.py")

        cmd = [
            "sudo",
            venv_python,
            main_py,
            "rc",
            anchor_name,
            target_path
        ]
        os.execvp("sudo", cmd)







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
    scripts = data.get("scripts", {})

    if not files:
        print(red("❌ No files found to restore in anchor."))
        return
    
    
    
    escalate_if_needed(files, target_path, anchor_name)


    # SHOW PREVIEW
    preview_changes = []
    for rel_path, file_data in files.items():
        is_absolute = rel_path.startswith("~") or rel_path.startswith("/")
        dest = os.path.expanduser(rel_path) if is_absolute else os.path.join(target_path, rel_path)

        if file_data.get("type") == "directory":
            if not os.path.isdir(dest):
                preview_changes.append(f"[DIR]  {dest}")
        elif not os.path.exists(dest):
            preview_changes.append(f"[NEW]  {dest}")
        else:
            try:
                content = file_data.get("content", "")
                encoding = file_data.get("encoding", "plain")
                decoded = base64.b64decode(content) if encoding == "base64" else content.encode()

                with open(dest, "rb") as f:
                    current_md5 = hashlib.md5(f.read()).digest()
                new_md5 = hashlib.md5(decoded).digest()

                if current_md5 != new_md5:
                    preview_changes.append(f"[CHG]  {dest}")
            except Exception as e:
                preview_changes.append(f"[???]  {dest} ({e})")

    if preview_changes:
        print(cyan("\n📝 The following files will be created or modified:\n"))
        for line in preview_changes:
            print("   " + line)
        choice = input(cyan("\n❓ Continue with these changes? [y/N]: ")).strip().lower()
        if choice != "y":
            print(red("❌ Aborted by user."))
            return
    else:
        print(green("✅ Nothing to do — all files already match."))
        return


    # Ejecutar preload si existe
    run_script_block(scripts.get("preload"), "preload")

    os.makedirs(target_path, exist_ok=True)

    for rel_path, file_data in files.items():
        is_absolute = rel_path.startswith("~") or rel_path.startswith("/")

        if is_absolute:
            dest = os.path.normpath(os.path.expanduser(rel_path))
        else:
            dest = os.path.normpath(os.path.join(target_path, rel_path))

        


        if file_data.get("type") == "directory":
            try:
                os.makedirs(dest, exist_ok=True)
                changed_files.append(dest)
            except Exception as e:
                print(red(f"❌ Failed to create directory {dest}: {e}"))
            continue

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



        # Restaurar permisos si se especificaron y el archivo fue cambiado
        perm = file_data.get("perm")
        if perm and os.path.isfile(dest):
            try:
                os.chmod(dest, int(perm, 8))
            except Exception as e:
                print(red(f"⚠️  Failed to apply permissions {perm} to {dest}: {e}"))





    if env_anchor:
        env_ref_path = os.path.abspath(os.path.join(target_path, ".anc_env"))
        try:
            with open(env_ref_path, "w") as f:
                f.write(env_anchor.strip() + "\n")
            print(green(f"🔗 Environment anchor reference created at {cyan(env_ref_path)}"))
            changed_files.append(env_ref_path)
        except Exception as e:
            print(red(f"❌ Failed to write .anc_env: {e}"))

    

    # Resumen final
    abs_paths = [p for p in files if p.startswith("~") or p.startswith("/")]
    rel_paths = [p for p in files if not (p.startswith("~") or p.startswith("/"))]

    print()

    if changed_files:
        print(green("✅ Modified or created:"))
        for path in changed_files:
            if os.path.isdir(path) and os.path.exists(path):
                print(f"[DIR]   {path}")
            else:
                print(f"        {path}")


    if skipped_files:
        print(cyan("⏭️  Skipped (already up to date):"))
        for path in skipped_files:
            print(f"   {path}")

    print()
    if abs_paths and rel_paths:
        print(green(f"✅ Files restored from anchor '{bold(anchor_name)}'."))
        print(cyan(f"  • Relative files under: {target_path}"))
        print(cyan(f"  • Absolute files to original locations"))
    elif rel_paths:
        print(green(f"✅ All files from anchor '{bold(anchor_name)}' restored under: {cyan(target_path)}"))
    else:
        print(green(f"✅ All files from anchor '{bold(anchor_name)}' restored to their original paths"))



    # Ejecutar postload si existe
    run_script_block(scripts.get("postload"), "postload")


def run(args):
    anchor_name = args.anchor
    dest_path = resolve_path(args.path or ".", base_dir=os.getcwd())
    recreate_from_anchor(anchor_name, dest_path)
