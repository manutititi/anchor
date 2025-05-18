import os
import subprocess
import tempfile
import json
import yaml

def handle_edit(args):
    input_name = args.name
    use_yaml = args.yml

    anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    editor = os.environ.get("EDITOR", "nano")

    # Definir rutas posibles
    anchor_path = os.path.abspath(os.path.join(anchor_dir, f"{input_name}.json"))
    direct_path = os.path.abspath(input_name)
    
    # Determinar cuál usar
    if os.path.isfile(anchor_path):
        path_to_edit = anchor_path
        origin = "anchor"
    elif os.path.isfile(direct_path):
        path_to_edit = direct_path
        origin = "file"
    else:
        print(f"❌ Archivo o anchor '{input_name}' no encontrado.")
        return 1

    if use_yaml:
        # Leer JSON
        try:
            with open(path_to_edit, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ No se pudo leer JSON: {e}")
            return 1

        # Guardar temporal como YAML
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".yml", delete=False) as tmp:
            yaml.dump(data, tmp, default_flow_style=False, sort_keys=False, allow_unicode=True)
            tmp_path = tmp.name

        # Editar YAML
        subprocess.call([editor, tmp_path])

        # Leer YAML actualizado y guardar como JSON
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                updated = yaml.safe_load(f)

            with open(path_to_edit, "w", encoding="utf-8") as f:
                json.dump(updated, f, indent=2, ensure_ascii=False)

            print(f"✅ {origin.capitalize()} '{input_name}' actualizado desde YAML.")
        except Exception as e:
            print(f"❌ Error al convertir YAML a JSON: {e}")
        finally:
            os.remove(tmp_path)
    else:
        subprocess.call([editor, path_to_edit])
