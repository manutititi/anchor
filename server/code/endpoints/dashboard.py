from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path
import json

router = APIRouter()

# Ruta absoluta al directorio de anchors
ANCHORS_DIR = Path(__file__).resolve().parent.parent.parent / "anchors"
ANCHORS_DIR.mkdir(parents=True, exist_ok=True)  # Asegura que exista

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    print("📁 Buscando anchors en:", ANCHORS_DIR)
    print("📄 Archivos encontrados:", list(ANCHORS_DIR.glob("*.json")))

    rows = []

    for file in ANCHORS_DIR.glob("*.json"):
        try:
            with open(file) as f:
                data = json.load(f)

            name = file.stem
            type_ = data.get("type", "")
            note = data.get("note", "")
            env = data.get("env", "")
            project = data.get("project", "")
            updated = data.get("last_updated", "")
            path_or_url = data.get("path") or data.get("endpoint", {}).get("base_url", "")

            row = f"""
                <tr>
                    <td><a href="/anchors/{name}/raw" target="_blank">{name}</a></td>
                    <td>{type_}</td>
                    <td>{env}</td>
                    <td>{project}</td>
                    <td>{note}</td>
                    <td>{path_or_url}</td>
                    <td>{updated}</td>
                </tr>
            """
            rows.append(row)

        except Exception as e:
            print(f" Error al leer {file.name}: {e}")
            continue

    html = f"""
    <html>
    <head>
        <title>Anchor Server Dashboard</title>
        <style>
            body {{ font-family: sans-serif; padding: 2rem; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
            th {{ background-color: #f4f4f4; }}
            a {{ text-decoration: none; color: #0366d6; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <h1>⚓ Anchor Server Dashboard</h1>
        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Env</th>
                    <th>Project</th>
                    <th>Note</th>
                    <th>Path / URL</th>
                    <th>Last Updated</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </body>
    </html>
    """

    return html
