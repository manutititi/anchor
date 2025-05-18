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


def load_anchor(name):
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Anchor '{name}' no encontrado en {DATA_DIR}")
    with open(path) as f:
        return json.load(f)


def build_inventory_multiple(anchors):
    """Genera un inventario INI para múltiples hosts ssh."""
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
    """Combina múltiples plantillas como un único playbook, envolviéndolas en un único Play."""
    combined_tasks = []

    for task in tasks:
        template_name = task["template"]

        # Soporte especial para template 'from_anchor'
        if template_name == "from_anchor":
            anchor_name = task.get("vars", {}).get("anchor")
            if not anchor_name:
                raise ValueError("Se requiere 'vars.anchor' para usar el template 'from_anchor'")
            expanded = expand_from_anchor(anchor_name)
            combined_tasks.extend(expanded)
            continue  # Salta el resto del ciclo

        template_path = TEMPLATES_DIR / f"{template_name}.yml"

        if not template_path.exists():
            raise FileNotFoundError(f"Template '{template_name}.yml' not found in {TEMPLATES_DIR}")

        with open(template_path) as f:
            content = f.read()

        loaded = yaml.safe_load(content)
        override = task.get("override", {})

        if isinstance(loaded, list):
            for t in loaded:
                t.update(override)
            combined_tasks.extend(loaded)
        elif isinstance(loaded, dict):
            loaded.update(override)
            combined_tasks.append(loaded)

    # Envolver todo en un único 'play'
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





def build_vars_file(tasks):
    merged_vars = {}

    for task in tasks:
        vars_ = task.get("vars", {})
        for key, value in vars_.items():
            if isinstance(value, list):
                merged_vars[key] = value
            elif isinstance(value, str) and value.strip().startswith('['):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        merged_vars[key] = parsed
                    else:
                        merged_vars[key] = [value]
                except Exception:
                    merged_vars[key] = [value]
            elif isinstance(value, str):
                merged_vars[key] = [value]
            else:
                merged_vars[key] = []

    for key in merged_vars:
        if not isinstance(merged_vars[key], list):
            merged_vars[key] = [merged_vars[key]]

    print("\n==== YAML generado para --extra-vars ====")
    print(yaml.safe_dump(merged_vars, default_flow_style=False))
    print("=========================================\n")

    temp = NamedTemporaryFile(delete=False, mode='w', suffix='.yml')
    yaml.safe_dump(merged_vars, temp, default_flow_style=False, allow_unicode=True, sort_keys=False)
    temp.close()
    return temp.name




def expand_from_anchor(anchor_name):
    """Genera tasks Ansible a partir de un anchor tipo 'files', con directorios implícitos y respeto a 'become'."""
    anchor_path = DATA_DIR / f"{anchor_name}.json"
    if not anchor_path.exists():
        raise FileNotFoundError(f"Files anchor '{anchor_name}' no encontrado en {DATA_DIR}")

    with open(anchor_path) as f:
        anchor_data = json.load(f)

    if anchor_data.get("type") != "files":
        raise ValueError(f"Anchor '{anchor_name}' no es de tipo 'files'")

    files = anchor_data.get("files", {})
    all_dirs = {}

    # Recoger todos los directorios necesarios (explícitos e implícitos)
    for raw_path, props in files.items():
        raw_path = raw_path.strip()

        if props.get("type") == "directory":
            all_dirs[raw_path] = props.get("become", False)

        elif props.get("mode") == "replace":
            parent_dir = os.path.dirname(raw_path)
            if parent_dir not in all_dirs:
                all_dirs[parent_dir] = props.get("become", False)

    tasks = []

    # Tareas para directorios, ordenadas para asegurar padres antes que hijos
    for d in sorted(all_dirs.keys(), key=len):
        tasks.append({
            "name": f"Ensure directory {d}",
            "ansible.builtin.file": {
                "path": d,
                "state": "directory",
                "mode": "0755"
            },
            "become": all_dirs[d]
        })

    # Tareas para archivos
    for raw_path, props in files.items():
        raw_path = raw_path.strip()
        if props.get("mode") == "replace" and "content" in props:
            tasks.append({
                "name": f"Write {os.path.basename(raw_path)}",
                "ansible.builtin.copy": {
                    "dest": raw_path,
                    "content": props["content"],
                    "force": True,
                    "mode": "0644"
                },
                "become": props.get("become", False)
            })

    return tasks









def handle_sible(args):
    try:
        play_anchor = load_anchor(args.anchor)

        if play_anchor["type"] != "ansible":
            raise ValueError("El anchor debe ser de tipo 'ansible'")

        if hasattr(args, "filter") and args.filter:
            matched = anchor_filter.filter_anchors(args.filter)
            host_anchors = [v for v in matched.values() if v.get("type") == "ssh"]
            if not host_anchors:
                raise ValueError(f"No se encontraron anchors tipo ssh con el filtro: {args.filter}")
        elif hasattr(args, "host") and args.host:
            host_names = [h.strip() for h in args.host.split(",")]
            host_anchors = [load_anchor(h) for h in host_names]
            for h in host_anchors:
                if h["type"] != "ssh":
                    raise ValueError(f"El host '{h['name']}' no es de tipo ssh")
        else:
            raise ValueError("Debes especificar uno o varios hosts, o usar -f para filtrar por metadatos.")

        inventory_file = build_inventory_multiple(host_anchors)
        playbook_file = build_playbook(play_anchor["ansible"]["tasks"])
        vars_file = build_vars_file(play_anchor["ansible"]["tasks"])

        extra_options = play_anchor["ansible"].get("options", [])
        if not isinstance(extra_options, list):
            raise ValueError("El campo 'options' debe ser una lista (ej: [\"-v\", \"--check\"])")

        subprocess.run([
            "ansible-playbook",
            "-i", inventory_file,
            playbook_file,
            f"--extra-vars=@{vars_file}",
            *extra_options
        ], check=True)

    finally:
        for file in [locals().get("inventory_file"),
                     locals().get("playbook_file"),
                     locals().get("vars_file")]:
            if file and os.path.exists(file):
                os.remove(file)
