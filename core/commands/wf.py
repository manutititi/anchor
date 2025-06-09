#core/commands/wf.py
import json
import time
import subprocess
from pathlib import Path
from jinja2 import Template
from core.utils.path import resolve_path
from core.utils.colors import red, green, cyan, bold
from typing import List, Union
import tempfile
import re
import os
import sys
from core.utils.secrets import resolve_secrets


DATA_DIR = Path(resolve_path("~/.anchors/data"))


def load_anchor(name_or_path):
    path = Path(name_or_path)
    if not path.exists():
        path = DATA_DIR / f"{name_or_path}.json"
    if not path.exists():
        raise FileNotFoundError(f"Workflow '{name_or_path}' not found")
    with open(path) as f:
        raw = f.read()
    return raw, path


def render(template_str, context):
    return Template(template_str).render(**context)




def escalate_if_needed_for_wf(tasks, workflow_data=None):
    if os.geteuid() == 0:
        return  # Ya somos root

    privileged_paths = []
    embedded_files = workflow_data.get("files", {}) if workflow_data else {}

    for task in tasks:
        anchor_name = task.get("files")
        if not anchor_name:
            continue

        # Buscar en workflow inline
        anchor_data = embedded_files.get(anchor_name)
        if anchor_data:
            files = anchor_data
        else:
            try:
                raw, _ = load_anchor(anchor_name)
                anchor = json.loads(raw)
                if anchor.get("type") != "files":
                    continue
                files = anchor.get("files", {})
            except Exception:
                continue

        for path_template, meta in files.items():
            become = meta.get("become", False)
            if become is True or path_template.startswith(("/etc", "/usr", "/opt", "/root", "/srv", "/var", "/tmp")):
                privileged_paths.append(path_template)

    if privileged_paths:
        print(red("\n⚠️  This workflow modifies files that require root permissions:\n"))
        for path in privileged_paths:
            print("   " + path)
        print()
        print(cyan("❓ Do you want to re-run the entire workflow with sudo?"))
        choice = input(cyan("   [y/N]: ")).strip().lower()
        if choice != "y":
            print(red("❌ Aborted by user."))
            sys.exit(1)

        # Relanzar el workflow completo con sudo y conservar el entorno
        anchor_arg = sys.argv[sys.argv.index("wf") + 1] if "wf" in sys.argv else ""
        anchor_root = os.path.expanduser("~/.anchors")
        venv_python = os.path.join(anchor_root, "venv", "bin", "python3")
        main_py = os.path.join(anchor_root, "core", "main.py")

        env = os.environ.copy()
        env["WF_NONINTERACTIVE"] = "1"

        cmd = ["sudo", "-E", venv_python, main_py, "wf", anchor_arg]
        os.execve("/usr/bin/sudo", cmd, env)





def run_rc(anchor_name, context={}):
    from core.commands.rc import recreate_from_anchor
    import tempfile
    import io
    import os
    from contextlib import redirect_stdout

    current_workflow = context.get("__workflow_data__")
    inline_files = current_workflow.get("files", {}) if current_workflow else {}
    inline_anchor = inline_files.get(anchor_name)

    if inline_anchor:
        data = {
            "type": "files",
            "name": f"__inline__{anchor_name}",
            "files": inline_anchor
        }
    else:
        try:
            raw, _ = load_anchor(anchor_name)
            data = json.loads(raw)
        except FileNotFoundError:
            print(red(f"❌ Anchor '{anchor_name}' not found in disk or workflow."))
            return 1
        if data.get("type") != "files":
            print(red(f"⚠️  Anchor '{anchor_name}' is not of type 'files'"))
            return 1

    # Renderizar
    rendered_files = {}
    for path_template, meta in data.get("files", {}).items():
        try:
            rendered_path = Template(path_template).render(**context)
        except Exception as e:
            print(red(f"❌ Error rendering path '{path_template}': {e}"))
            return 1

        if "{{" in rendered_path or "}}" in rendered_path:
            print(red(f"❌ Path '{rendered_path}' not fully rendered."))
            print(cyan("→ Context used:"))
            print(json.dumps(context, indent=2))
            return 1

        rendered_meta = {}
        for k, v in meta.items():
            if isinstance(v, str):
                try:
                    rendered_meta[k] = Template(v).render(**context)
                except Exception as e:
                    print(red(f"❌ Error rendering key '{k}' in '{rendered_path}': {e}"))
                    return 1
            else:
                rendered_meta[k] = v

        rendered_files[rendered_path] = rendered_meta

    data["files"] = rendered_files
    data["name"] = f"{anchor_name}__rendered__"

    # Aplicar con captura
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor_path = os.path.join(tmpdir, f"{anchor_name}.json")
        with open(anchor_path, "w") as f:
            json.dump(data, f, indent=2)
        os.environ["ANCHOR_DIR"] = tmpdir

        f = io.StringIO()
        with redirect_stdout(f):
            recreate_from_anchor(anchor_name, context.get("target_path", "."))

        captured = f.getvalue().strip().splitlines()

        # Mostrar solo una línea por archivo modificado
        already_shown = set()
        for line in captured:
            line = line.strip()
            if line.startswith("[NEW]") or line.startswith("[MOD]"):
                path = line.split("]", 1)[-1].strip()
                if path not in already_shown:
                    print(green(f"    ✅ File created or modified: {path}"))
                    already_shown.add(path)

        if not already_shown:
            print(cyan("    ℹ️ No changes (Already present)"))

    return 0
















def execute_with_input_auto(command: str, inputs: List[Union[str, dict]], cwd: str = None, timeout: int = 15):
    # Generar script expect robusto
    script_lines = [f"spawn -noecho {command}"]

    for entry in inputs:
        if isinstance(entry, dict):
            for pattern, value in entry.items():
                script_lines.append(f'expect "{pattern}"')
                script_lines.append(f'send "{value}\\r"')
        else:
            # patrón genérico si no se especifica
            script_lines.append('expect ".*:"')
            script_lines.append(f'send "{entry}\\r"')

    script_lines.append("expect eof")

    with tempfile.NamedTemporaryFile("w", suffix=".exp", delete=False) as temp:
        temp.write("\n".join(script_lines))
        temp_path = temp.name

    try:
        result = subprocess.run(
            ["expect", temp_path],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return 1, '', 'Timed out waiting for expected input.'
    finally:
        Path(temp_path).unlink(missing_ok=True)

    return result.returncode, result.stdout, result.stderr








def expand_loop(task_loop, context):
    if isinstance(task_loop, list):
        return task_loop
    elif isinstance(task_loop, dict):
        rendered = {}
        for k, v in task_loop.items():
            if isinstance(v, str):
                rendered_val = render(v, context).strip()
                try:
                    rendered[k] = eval(rendered_val, {}, {})
                except Exception:
                    try:
                        rendered[k] = json.loads(rendered_val)
                    except Exception:
                        rendered[k] = [x.strip() for x in rendered_val.split(',')]
            else:
                rendered[k] = v
        length = len(next(iter(rendered.values())))
        return [
            {key: rendered[key][i] for key in rendered}
            for i in range(length)
        ]
    else:
        raise ValueError("'loop' must be a list or a dictionary")


def extract_output_field(task):
    for key in task:
        if key.startswith("output"):
            append = key.endswith(">>")
            return key, task[key], append
    return None, None, False

def execute_task(task, global_vars, task_results):
    task_vars = task.get("vars", {})
    merged_vars = {**global_vars, **task_vars, **task_results}
    name = render(task.get("name", "Unnamed task"), merged_vars)
    register_key = task.get("set") or task.get("register")

    output_key, output_file, append = extract_output_field(task)

    if "loop" in task:
        iterations = expand_loop(task["loop"], merged_vars)
        for idx, loop_vars in enumerate(iterations, 1):
            context = {**merged_vars, **loop_vars}

            if "_input_cache" not in global_vars:
                global_vars["_input_cache"] = {}
            context["_input_cache"] = global_vars["_input_cache"]

            loop_name = render(task.get("name", "Unnamed task"), context)
            if not _should_run(task, context):
                print(cyan(f"  • {loop_name} [loop {idx}/{len(iterations)}] skipped"))
                continue

            print(bold(f"  • {loop_name} [loop {idx}/{len(iterations)}]"))
            retcode, stdout, stderr = _execute_single(task, context, output_file=output_file, append=append)

            if register_key:
                task_results[register_key] = stdout.strip() if stdout is not None else ''
            task_results[task["id"]] = retcode
            global_vars.update({k: v for k, v in context.items() if k not in global_vars})
        print()

    else:
        if not _should_run(task, merged_vars):
            print(cyan(f"  • {name} skipped"))
            if register_key:
                task_results[register_key] = ''
            task_results[task["id"]] = -1  # para que no se evalúe como éxito
            print()
            return

        if "_input_cache" not in global_vars:
            global_vars["_input_cache"] = {}
        merged_vars["_input_cache"] = global_vars["_input_cache"]

        print(bold(f"  • {name}"))
        retcode, stdout, stderr = _execute_single(task, merged_vars, output_file=output_file, append=append)

        if register_key:
            task_results[register_key] = stdout.strip() if stdout is not None else ''
        task_results[task["id"]] = retcode  # ✅ guardar siempre el código de retorno

        global_vars.update({k: v for k, v in merged_vars.items() if k not in global_vars})
        print()





def _should_run(task, context):
    if "when" not in task:
        return True
    expr = render(task["when"], context)
    try:
        return eval(expr, {}, context)
    except Exception as e:
        print(red(f"    → when eval failed: {e}"))
        return False


def _write_output(path, mode, stdout, stderr):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode) as f:
        if stdout:
            f.write(stdout)
        if stderr:
            f.write(stderr)



def resolve_undefined_vars(template_str, context):
    if "_input_cache" not in context:
        context["_input_cache"] = {}
    input_cache = context["_input_cache"]

    variables = re.findall(r"{{\s*([\w_]+)\s*}}", template_str)
    for var in variables:
        if var not in context:
            if var in input_cache:
                context[var] = input_cache[var]
            else:
                user_input = input(f"    🧩 Var '{var}' not defined, insert a value: ").strip()
                context[var] = user_input
                input_cache[var] = user_input



def _execute_single(task, context, output_file=None, append=False):
    import requests
    import jmespath

    mode = "a" if append else "w"
    cwd = None

    if "chdir" in task:
        cwd_path = render(task["chdir"], context)
        cwd = str(Path(cwd_path).expanduser())
        print(cyan(f"    → chdir: {cwd}"))

    if output_file:
        output_file = resolve_secrets(render(output_file, context))
        output_file = str(Path(output_file).expanduser())

    if "sleep" in task:
        print(cyan(f"    → sleep {task['sleep']}s"))
        time.sleep(task["sleep"])
        return 0, '', ''

    if "shell" in task:
        cmd_template = task["shell"]

        if "{{" in cmd_template:
            print(f"    🔍 Comando con variables: {cmd_template}")
            resolve_undefined_vars(cmd_template, context)

        cmd = resolve_secrets(render(cmd_template, context))

        if "input_auto" in task:
            inputs = []
            for x in task["input_auto"]:
                if isinstance(x, dict):
                    rendered_entry = {resolve_secrets(render(k, context)): resolve_secrets(render(v, context)) for k, v in x.items()}
                    inputs.append(rendered_entry)
                else:
                    inputs.append(resolve_secrets(render(x, context)))
            print(cyan(f"    → shell (input_auto): {cmd}"))
            return execute_with_input_auto(cmd, inputs, cwd=cwd)

        print(cyan(f"    → shell: {cmd}"))
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)

        if output_file and (result.stdout or result.stderr):
            _write_output(output_file, mode, result.stdout, result.stderr)

        if not output_file and not task.get("register") and result.stdout:
            print(result.stdout.strip())

        if result.returncode == 0:
            print(green(f"    ✔️ OK ({result.returncode})"))
        else:
            print(red(f"    ❌ FAIL ({result.returncode})"))
        return result.returncode, result.stdout, result.stderr

    elif "anc" in task:
        cmd_template = task["anc"]
        resolve_undefined_vars(cmd_template, context)
        cmd = resolve_secrets(render(cmd_template, context))
        print(cyan(f"    → anc: {cmd}"))
        source_functions = 'for f in "$HOME/.anchors/functions/"*.sh; do source "$f"; done'
        full_cmd = f"{source_functions} && anc {cmd}"

        result = subprocess.run(["bash", "-i", "-c", full_cmd], cwd=cwd, capture_output=True, text=True)

        if output_file and (result.stdout or result.stderr):
            _write_output(output_file, mode, result.stdout, result.stderr)

        if not output_file and not task.get("register") and result.stdout:
            print(result.stdout.strip())

        if result.returncode == 0:
            print(green(f"    ✔️ OK ({result.returncode})"))
        else:
            print(red(f"    ❌ anc command failed with code {result.returncode}"))

        return result.returncode, result.stdout, result.stderr

    elif "files" in task:
        anchor_name = resolve_secrets(render(task["files"], context))
        print(cyan(f"    → files: applying anchor '{anchor_name}' with context"))
        returncode = run_rc(anchor_name, context)
        return 0, '', ''

    elif "api" in task:
        api = task["api"]
        method = api.get("method", "GET").upper()
        mode = api.get("mode", "json")
        extract_expr = api.get("extract")
        register_key = task.get("set") or task.get("register")


        resolve_undefined_vars(api["url"], context)

        for val in api.get("headers", {}).values():
            resolve_undefined_vars(val, context)

        if "body" in api:
            if isinstance(api["body"], str):
                resolve_undefined_vars(api["body"], context)
            elif isinstance(api["body"], dict):
                resolve_undefined_vars(json.dumps(api["body"]), context)

        for val in api.get("params", {}).values():
            resolve_undefined_vars(val, context)

        url = resolve_secrets(render(api["url"], context))
        headers = {k: resolve_secrets(render(v, context)) for k, v in api.get("headers", {}).items()}
        params = {k: resolve_secrets(render(v, context)) for k, v in api.get("params", {}).items()} if api.get("params") else {}

        body = api.get("body")
        if isinstance(body, str):
            body = resolve_secrets(render(body, context))
        elif isinstance(body, dict):
            body = json.loads(resolve_secrets(render(json.dumps(body), context)))

        print(cyan(f"    → API {method} {url}"))

        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, params=params)
            else:
                if mode == "json":
                    resp = requests.request(method, url, headers=headers, json=body, params=params)
                elif mode == "form":
                    resp = requests.request(method, url, headers=headers, data=body, params=params)
                elif mode == "raw":
                    resp = requests.request(method, url, headers=headers, data=json.dumps(body), params=params)
                else:
                    print(red(f"    ❌ Unsupported API mode: {mode}"))
                    return 1, "", "Unsupported API mode"

            resp.raise_for_status()
            print(green(f"    ✔️ {resp.status_code}"))

            raw_result = resp.text
            result = raw_result

            if extract_expr:
                try:
                    json_data = resp.json()
                    result = jmespath.search(extract_expr, json_data)
                    if isinstance(result, (dict, list)):
                        result = json.dumps(result, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(red(f"    ⚠️ Failed to extract '{extract_expr}': {e}"))
                    result = raw_result

            if register_key:
                context[register_key] = result
                print(cyan(f"    ⤷ Stored response in var: {register_key}"))

            return 0, result, ""

        except Exception as e:
            print(red(f"    ❌ API error: {e}"))
            return 1, "", str(e)














def handle_wf(args):
    raw, json_path = load_anchor(args.anchor)
    data = json.loads(raw)

    if data.get("type") != "workflow":
        raise ValueError("Anchor must be of type 'workflow'")

    raw_vars = data.get("vars", {})
    global_vars = {k: resolve_secrets(v) if isinstance(v, str) else v for k, v in raw_vars.items()}


    tasks = data.get("workflow", {}).get("tasks", [])

    # 🔐 Escalado anticipado si alguna tarea necesita root
    escalate_if_needed_for_wf(tasks, workflow_data=data)


    # Verificar y asignar IDs si faltan
    any_missing = False
    for i, task in enumerate(tasks, 1):
        if "id" not in task:
            task["id"] = f"task_{i}"
            any_missing = True

    if any_missing:
        print(red("[!] Some tasks were missing 'id'. IDs have been assigned automatically."))
        print(red("[!] Please review the workflow file and re-run."))
        for task in tasks:
            print(f"   - {task.get('name', 'Unnamed')} → id='{task['id']}'")
        data['workflow']['tasks'] = tasks
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(red(f"[!] Updated: {json_path}"))
        print(red("[!] Aborting execution.\n"))
        return

    task_results = {}
    print(bold(f"Workflow: {data.get('name', '')}"))
    print()

    # Inyectar workflow completo en el contexto
    global_vars["__workflow_data__"] = data

    for i, task in enumerate(tasks, 1):
        name = render(task.get("name", "Unnamed"), global_vars)
        print(bold(f"Task {i}/{len(tasks)}: {name} (id: {task['id']})"))
        execute_task(task, global_vars, task_results)

    print(green("Workflow completed."))

