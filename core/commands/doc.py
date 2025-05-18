import os
import json
from datetime import datetime

TYPE_DESCRIPTIONS = {
    "files": "Files and directories that can be recreated from embedded content.",
    "env": "Working environment with preload/postload scripts.",
    "ssh": "Remote machine accessible via SSH.",
    "url": "HTTP endpoint or REST API.",
    "docker": "Service based on docker-compose.",
    "ansible": "Ansible tasks for infrastructure automation.",
    "local": "Local path without specific structure.",
    "ldap": "LDAP user or group entry.",
}

def generate_doc(anchor_name, output_path=None, print_stdout=False):
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    anchor_path = os.path.join(anchor_dir, f"{anchor_name}.json")

    if not os.path.isfile(anchor_path):
        print(f"❌ Anchor '{anchor_name}' not found.")
        return 1

    with open(anchor_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = [f"# Anchor: {anchor_name}", ""]

    anchor_type = data.get("type", "unknown")
    lines.append(f"- **Type**: {anchor_type}")
    desc = TYPE_DESCRIPTIONS.get(anchor_type, None)
    if desc:
        lines.append(f"- **Description**: {desc}")

    path = data.get("path", "(not specified)")
    lines.append(f"- **Base path**: `{path}`")
    lines.append(f"- **Created by**: {data.get('created_by', '-')}")
    if "last_updated" in data:
        dt = data["last_updated"].split("T")[0] + " " + data["last_updated"].split("T")[1].split(".")[0]
        lines.append(f"- **Last updated**: {dt}")
    if "updated_by" in data:
        lines.append(f"- **Updated by**: {data['updated_by']}")
    lines.append("")

    # File list for type: files
    if anchor_type == "files" and "files" in data:
        lines.append("## Included files\n")
        lines.append("| Relative path | Type | Mode | Content |")
        lines.append("|---------------|------|------|---------|")
        for full_path, props in data["files"].items():
            name = full_path.replace(data["path"], "").lstrip("/").lstrip("~")
            ftype = props.get("type", "file")
            mode = props.get("mode", "-")
            encoding = props.get("encoding", "n/a") if ftype != "directory" else "—"
            lines.append(f"| `{name}` | {ftype} | {mode} | {encoding} |")
        lines.append("")

    # Scripts
    if "scripts" in data:
        lines.append("## Scripts\n")
        for key in ["preload", "postload"]:
            val = data["scripts"].get(key)
            if val:
                lines.append(f"### {key.capitalize()}")
                if isinstance(val, list):
                    for v in val:
                        lines.append(f"- `{v}`")
                else:
                    lines.append(f"- `{val}`")
                lines.append("")

    # Endpoint
    if anchor_type == "url" and "endpoint" in data:
        lines.append("## Endpoint configuration\n")
        endpoint = data["endpoint"]
        lines.append(f"- **Base URL**: `{endpoint.get('base_url', '-')}`")
        if "methods" in endpoint:
            lines.append(f"- **Allowed methods**: `{', '.join(endpoint['methods'])}`")
        if "auth" in endpoint:
            lines.append("- **Auth:**")
            for k, v in endpoint["auth"].items():
                lines.append(f"  - {k}: `{v}`")
        lines.append("")

    # SSH details
    if anchor_type == "ssh":
        lines.append("## SSH Configuration\n")
        lines.append(f"- **Host**: `{data.get('host', '-')}`")
        lines.append(f"- **User**: `{data.get('user', '-')}`")
        lines.append(f"- **Port**: `{data.get('port', '-')}`")
        lines.append(f"- **Identity file**: `{data.get('identity_file', '-')}`")
        lines.append("")

    # Ansible
    if anchor_type == "ansible":
        ansible_section = data.get("ansible", {})
        tasks = ansible_section.get("tasks", [])
        options = ansible_section.get("options", [])

        if tasks:
            lines.append("## Ansible tasks\n")
            for idx, task in enumerate(tasks, start=1):
                tmpl = task.get("template", "—")
                lines.append(f"### Task {idx}")
                lines.append(f"- **Template**: `{tmpl}`")

                vars_ = task.get("vars", {})
                if vars_:
                    lines.append("- **Variables:**")
                    for k, v in vars_.items():
                        if isinstance(v, list):
                            lines.append(f"  - `{k}`:")
                            for item in v:
                                lines.append(f"    - `{item}`")
                        else:
                            lines.append(f"  - `{k}`: `{v}`")

                override = task.get("override", {})
                if override:
                    lines.append("- **Overrides:**")
                    for module, config in override.items():
                        lines.append(f"  - `{module}`:")
                        if isinstance(config, dict):
                            for k, v in config.items():
                                lines.append(f"    - `{k}`: `{v}`")
                        elif isinstance(config, list):
                            for item in config:
                                lines.append(f"    - `{item}`")
                        else:
                            lines.append(f"    - `{config}`")
                lines.append("")

        if options:
            lines.append("### Ansible CLI options\n")
            lines.append(f"`{' '.join(options)}`\n")

    # Groups (universal)
    if "groups" in data:
        lines.append("## Groups\n")
        groups = data["groups"]
        if isinstance(groups, list):
            for g in groups:
                lines.append(f"- `{g}`")
        else:
            lines.append(f"- `{groups}`")
        lines.append("")

    # Suggested commands
    lines.append("## Suggested commands\n")
    lines.append("```bash")
    lines.append(f"anc show {anchor_name}")
    lines.append(f"anc edit {anchor_name} --yml")
    if anchor_type == "files":
        lines.append(f"anc cr {anchor_name} ./output/")
    elif anchor_type == "env":
        lines.append(f"anc env apply {anchor_name}")
    elif anchor_type == "ansible":
        lines.append(f"anc sible {anchor_name} host1")
    elif anchor_type == "ssh":
        lines.append(f"anc run {anchor_name} uptime")
        lines.append(f"anc sible <ansible-anchor> {anchor_name}")
    lines.append("```\n")
    lines.append("_Generated by `anc doc`_")

    markdown = "\n".join(lines)

    if print_stdout:
        print(markdown)
    else:
        output = output_path or f"{anchor_name}.md"
        with open(output, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"✅ Documentation written to {output}")
