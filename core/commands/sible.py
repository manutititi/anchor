import json
import os
import subprocess
import yaml
from pathlib import Path
from tempfile import NamedTemporaryFile

from core.utils.path import resolve_path
from core.utils import filter as anchor_filter

DATA_DIR = Path(resolve_path("~/.anchors/data"))
TEMPLATES_DIR = Path(resolve_path("~/.anchors/templates"))





def translate_script_block(scripts, when="preload"):
    if not scripts:
        return []

    tasks = []

    for s in scripts:
        if isinstance(s, str):
            cmd = s
            scope = "."
            become = False
        else:
            cmd = s.get("run")
            scope = s.get("scope", ".")
            become = s.get("become")

        # Traducir ~ → /home/{{ ansible_user }}
        if scope.startswith("~"):
            scope = scope.replace("~", "/home/{{ ansible_user }}", 1)

        if become is None:
            become = scope.startswith((
                "/etc", "/usr", "/opt", "/var", "/root"
            ))

        tasks.append({
            "name": f"[{when}] {cmd}",
            "ansible.builtin.shell": cmd,
            "args": {"chdir": scope},
            "become": become
        })

    return tasks







def load_anchor(name):
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Anchor '{name}' no encontrado en {DATA_DIR}")
    with open(path) as f:
        return json.load(f)


def build_inventory_multiple(anchors):
    lines = []
    for a in anchors:
        line = (
            f"{a['name']} "
            f"ansible_host={a['host']} "
            f"ansible_user={a['user']} "
            f"ansible_port={a.get('port', 22)} "
            f"ansible_ssh_private_key_file={resolve_path(a['identity_file'])}"
        )
        lines.append(line)

    temp = NamedTemporaryFile(delete=False, mode='w', suffix='.ini')
    temp.write("[all]\n" + "\n".join(lines))
    temp.close()
    return temp.name


def build_playbook(tasks):
    combined_tasks = []

    for task in tasks:
        # Si es una task ya expandida (como desde expand_from_anchor)
        if "ansible.builtin.copy" in task or "ansible.builtin.file" in task or "ansible.builtin.shell" in task:
            combined_tasks.append(task)
            continue

        # Aquí asumimos que es una task de plantilla (tipo "ansible")
        template_name = task["template"]

        if template_name == "from_anchor":
            anchor_name = task.get("vars", {}).get("anchor")
            if not anchor_name:
                raise ValueError("Se requiere 'vars.anchor' para usar el template 'from_anchor'")
            expanded = expand_from_anchor(anchor_name)
            combined_tasks.extend(expanded)
            continue

        template_path = TEMPLATES_DIR / f"{template_name}.yml"
        if not template_path.exists():
            raise FileNotFoundError(f"Template '{template_name}.yml' not found in {TEMPLATES_DIR}")

        with open(template_path) as f:
            loaded = yaml.safe_load(f)

        override = task.get("override", {})
        if isinstance(loaded, list):
            for t in loaded:
                if "vars" in task and isinstance(task["vars"], dict):
                    t["vars"] = task["vars"]
                t.update(override)
            combined_tasks.extend(loaded)
        elif isinstance(loaded, dict):
            if "vars" in task and isinstance(task["vars"], dict):
                loaded["vars"] = task["vars"]
            loaded.update(override)
            combined_tasks.append(loaded)

    full_play = [{
        "name": "Ansible Play from anchor",
        "hosts": "all",
        "become": True,
        "tasks": combined_tasks
    }]

    temp = NamedTemporaryFile(delete=False, mode='w', suffix='.yml')
    yaml.safe_dump(full_play, temp, default_flow_style=False, sort_keys=False, allow_unicode=True)
    temp.close()
    return temp.name





def expand_from_anchor(anchor_name):
    anchor_path = DATA_DIR / f"{anchor_name}.json"
    if not anchor_path.exists():
        raise FileNotFoundError(f"Files anchor '{anchor_name}' no encontrado en {DATA_DIR}")

    with open(anchor_path) as f:
        anchor_data = json.load(f)

    if anchor_data.get("type") != "files":
        raise ValueError(f"Anchor '{anchor_name}' no es de tipo 'files'")

    files = anchor_data.get("files", {})
    scripts = anchor_data.get("scripts", {})
    all_dirs = {}

    for raw_path, props in files.items():
        raw_path = raw_path.strip()
        if props.get("type") == "directory":
            all_dirs[raw_path] = props.get("become", False)
        elif props.get("mode") == "replace":
            parent_dir = os.path.dirname(raw_path)
            if parent_dir not in all_dirs:
                all_dirs[parent_dir] = props.get("become", False)

    tasks = []

    # PRELOAD scripts
    tasks += translate_script_block(scripts.get("preload"), "preload")

    # Ensure directories
    for d in sorted(all_dirs.keys(), key=len):
        dir_data = files.get(d, {})
        perm = dir_data.get("perm", "0755")

        tasks.append({
            "name": f"Ensure directory {d}",
            "ansible.builtin.file": {
                "path": d,
                "state": "directory",
                "mode": perm
            },
            "become": all_dirs[d]
        })


    # Copy files
    for raw_path, props in files.items():
        raw_path = raw_path.strip()
        if props.get("mode") == "replace" and "content" in props:
            copy_task = {
                "dest": raw_path,
                "content": props["content"],
                "force": True
            }

            if "perm" in props:
                copy_task["mode"] = props["perm"]
            else:
                copy_task["mode"] = "0644"

            tasks.append({
                "name": f"Write {os.path.basename(raw_path)}",
                "ansible.builtin.copy": copy_task,
                "become": props.get("become", False)
            })
        

    # POSTLOAD scripts
    tasks += translate_script_block(scripts.get("postload"), "postload")

    return tasks





def build_vars_file(tasks):
    merged_vars = {}
    for task in tasks:
        vars_ = task.get("vars", {})
        for key, value in vars_.items():
            if key == "local_path" and isinstance(value, str) and value.startswith("~"):
                merged_vars[key] = str(Path(value).expanduser())
            else:
                merged_vars[key] = value  # keep exact type
    return merged_vars


def handle_sible(args):
    try:
        play_anchor = load_anchor(args.anchor)
        anchor_type = play_anchor.get("type")

        if anchor_type not in ["ansible", "files"]:
            raise ValueError("El anchor debe ser de tipo 'ansible' o 'files'")

        # Cargar hosts
        if hasattr(args, "filter") and args.filter:
            matched = anchor_filter.filter_anchors(args.filter)
            host_anchors = [v for v in matched.values() if v.get("type") == "ssh"]
            if not host_anchors:
                raise ValueError(f"No se encontraron anchors tipo ssh con el filtro: {args.filter}")
        elif hasattr(args, "host") and args.host:
            host_names = [h.strip() for h in args.host.split(",")]
            host_anchors = [load_anchor(h) for h in host_names]
            for h in host_anchors:
                if h.get("type") != "ssh":
                    raise ValueError(f"El host '{h['name']}' no es de tipo ssh")
        else:
            raise ValueError("Debes especificar uno o varios hosts, o usar -f para filtrar por metadatos.")

        inventory_file = build_inventory_multiple(host_anchors)

        # Construir tasks dependiendo del tipo de anchor
        if anchor_type == "ansible":
            tasks = play_anchor["ansible"]["tasks"]
            extra_options = play_anchor["ansible"].get("options", [])
        elif anchor_type == "files":
            tasks = expand_from_anchor(args.anchor)
            extra_options = []

        playbook_file = build_playbook(tasks)

        merged_vars = build_vars_file(tasks)
        merged_vars["anchor"] = [play_anchor["name"]]
        merged_vars["ssh_by_host"] = {
            h["name"]: {
                "host": h["host"],
                "user": h["user"],
                "port": h.get("port", 22),
                "identity_file": resolve_path(h["identity_file"])
            }
            for h in host_anchors
        }

        print("\n==== YAML generado para --extra-vars ====")
        print(yaml.safe_dump(merged_vars, default_flow_style=False))
        print("=========================================\n")

        vars_file = NamedTemporaryFile(delete=False, mode='w', suffix='.yml')
        yaml.safe_dump(merged_vars, vars_file, default_flow_style=False, allow_unicode=True, sort_keys=False)
        vars_file.close()

        if not isinstance(extra_options, list):
            raise ValueError("El campo 'options' debe ser una lista (ej: [\"-v\", \"--check\"])")

        subprocess.run([
            "ansible-playbook",
            "-i", inventory_file,
            playbook_file,
            f"--extra-vars=@{vars_file.name}",
            *extra_options
        ], check=True)

    finally:
        for file in [locals().get("inventory_file"),
                     locals().get("playbook_file"),
                     locals().get("vars_file").name if "vars_file" in locals() else None]:
            if file and os.path.exists(file):
                os.remove(file)
