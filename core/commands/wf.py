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





def run_rc(anchor_name, vars={}):
    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    anchor_path = os.path.join(anchor_dir, f"{anchor_name}.json")

    if not os.path.exists(anchor_path):
        print(f"⚠️  Anchor '{anchor_name}' not found at {anchor_path}")
        return 1

    with open(anchor_path) as f:
        data = json.load(f)

    if data.get("type") != "files":
        print(f"⚠️  Anchor '{anchor_name}' is not of type 'files'")
        return 1

    files = data.get("files", {})
    rendered = {}

    for path, meta in files.items():
        rendered_path = Template(path).render(**vars)
        rendered[rendered_path] = {}

        for k, v in meta.items():
            if isinstance(v, str):
                rendered[rendered_path][k] = Template(v).render(**vars)
            else:
                rendered[rendered_path][k] = v

    # ✅ Importar desde rc (no desde cr)
    from core.commands.rc import apply_file_tasks
    return apply_file_tasks(rendered)



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
    register_key = task.get("register")
    output_key, output_file, append = extract_output_field(task)

    if "loop" in task:
        iterations = expand_loop(task["loop"], merged_vars)
        for idx, loop_vars in enumerate(iterations, 1):
            context = {**merged_vars, **loop_vars}

            # Inicializar caché compartido por tareas
            if "_input_cache" not in global_vars:
                global_vars["_input_cache"] = {}
            context["_input_cache"] = global_vars["_input_cache"]

            loop_name = render(task.get("name", "Unnamed task"), context)
            if not _should_run(task, context):
                print(cyan(f"  • {loop_name} [loop {idx}/{len(iterations)}] skipped"))
                continue
            print(bold(f"  • {loop_name} [loop {idx}/{len(iterations)}]"))
            retcode, stdout, stderr = _execute_single(task, context, output_file=output_file, append=append)

            # Registrar resultados y actualizar variables globales
            if register_key:
                task_results[register_key] = stdout.strip() if stdout is not None else ''
            global_vars.update({k: v for k, v in context.items() if k not in global_vars})
        print()  # espacio después del loop
    else:
        if not _should_run(task, merged_vars):
            print(cyan(f"  • {name} skipped"))
            if register_key:
                task_results[register_key] = ''
            else:
                task_results[task['id']] = 0
            print()
            return

        # Inicializar caché compartido
        if "_input_cache" not in global_vars:
            global_vars["_input_cache"] = {}
        merged_vars["_input_cache"] = global_vars["_input_cache"]

        print(bold(f"  • {name}"))
        retcode, stdout, stderr = _execute_single(task, merged_vars, output_file=output_file, append=append)

        if register_key:
            task_results[register_key] = stdout.strip() if stdout is not None else ''
        else:
            task_results[task['id']] = retcode

        # Actualizar global_vars con nuevas entradas definidas en el contexto
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


def _execute_single(task, context, output_file=None, append=False):
    mode = "a" if append else "w"
    cwd = None

    if "chdir" in task:
        cwd_path = render(task["chdir"], context)
        cwd = str(Path(cwd_path).expanduser())
        print(cyan(f"    → chdir: {cwd}"))

    if output_file:
        output_file = render(output_file, context)
        output_file = str(Path(output_file).expanduser())

    if "sleep" in task:
        print(cyan(f"    → sleep {task['sleep']}s"))
        time.sleep(task["sleep"])
        return 0, '', ''

    if "shell" in task:
        cmd_template = task["shell"]

        if "{{" in cmd_template:
            print(f"    🔍 Comando con variables: {cmd_template}")

        # Inicializar cache de input
        if "_input_cache" not in context:
            context["_input_cache"] = {}
        input_cache = context["_input_cache"]

        # Detectar variables {{ var }}
        undefined_vars = re.findall(r"{{\s*([\w_]+)\s*}}", cmd_template)
        for var in undefined_vars:
            if var not in context:
                if var in input_cache:
                    context[var] = input_cache[var]
                else:
                    user_input = input(f"    🧩 Var '{var}' not defined, insert a value: ").strip()
                    context[var] = user_input
                    input_cache[var] = user_input

        cmd = render(cmd_template, context)

        if "input_auto" in task:
            inputs = []
            for x in task["input_auto"]:
                if isinstance(x, dict):
                    rendered_entry = {render(k, context): render(v, context) for k, v in x.items()}
                    inputs.append(rendered_entry)
                else:
                    inputs.append(render(x, context))
            print(cyan(f"    → shell (input_auto): {cmd}"))
            return execute_with_input_auto(cmd, inputs, cwd=cwd)

        print(cyan(f"    → shell: {cmd}"))
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)

        if output_file and (result.stdout or result.stderr):
            _write_output(output_file, mode, result.stdout, result.stderr)

        if not output_file and not task.get("register") and result.stdout:
            print(result.stdout.strip())

        return result.returncode, result.stdout, result.stderr

    elif "anc" in task:
        cmd = render(task["anc"], context)
        print(cyan(f"    → anc: {cmd}"))
        source_functions = 'for f in "$HOME/.anchors/functions/"*.sh; do source "$f"; done'
        full_cmd = f"{source_functions} && anc {cmd}"
        result = subprocess.run(["bash", "-i", "-c", full_cmd], cwd=cwd)
        if output_file:
            print(red("⚠️ Output redirection not supported in interactive mode (anc task)"))
        if result.returncode != 0:
            print(red(f"    ❌ anc command failed with code {result.returncode}"))
        return result.returncode, '', ''

    elif "files" in task:
        anchor_name = render(task["files"], context)
        print(cyan(f"    → files: applying anchor '{anchor_name}' with context"))
        returncode = run_rc(anchor_name, context)
        return returncode, "", ""

    return 0, '', ''










def handle_wf(args):
    raw, json_path = load_anchor(args.anchor)
    data = json.loads(raw)

    if data.get("type") != "workflow":
        raise ValueError("Anchor must be of type 'workflow'")

    global_vars = data.get("vars", {})
    tasks = data.get("workflow", {}).get("tasks", [])
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
    for i, task in enumerate(tasks, 1):
        name = render(task.get("name", "Unnamed"), global_vars)
        print(bold(f"Task {i}/{len(tasks)}: {name} (id: {task['id']})"))
        execute_task(task, global_vars, task_results)
    print(green("Workflow completed."))
