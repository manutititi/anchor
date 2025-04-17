from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
from typing import List
from datetime import datetime, timezone
import shutil
import json
import re
import os

app = FastAPI()
ANCHORS_DIR = Path("anchors")
EXTERNAL_DIR = Path("external_files")
ANCHORS_DIR.mkdir(parents=True, exist_ok=True)
EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)

# --- Filtros compatibles con la app ---

def get_nested(d, key):
    parts = key.split(".")
    for part in parts:
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d

def normalize_value(value):
    if isinstance(value, str):
        v = value.lower()
        if v == "true":
            return True
        if v == "false":
            return False
        if v.isdigit():
            return int(v)
    return value

def expr_to_lambda(expr_str):
    expr_str = expr_str.replace(" AND ", " and ").replace(" OR ", " or ")
    pattern = re.compile(r'([a-zA-Z0-9_.]+)\s*(!=|=|~|!~)\s*("[^"]+"|[^\s()]+)')
    var_map = {}

    for i, (key, op, val) in enumerate(pattern.findall(expr_str)):
        var_name = f"_v{i}"
        full_expr = f"{key}{op}{val}"
        expr_str = expr_str.replace(full_expr, var_name)
        var_map[var_name] = (key.strip(), op.strip(), normalize_value(val.strip('"')))

    def matcher(data):
        env = {}
        for var_name, (key, op, expected) in var_map.items():
            actual = get_nested(data, key)
            if op == "=":
                env[var_name] = (actual == expected)
            elif op == "!=":
                env[var_name] = (actual != expected)
            elif op == "~":
                env[var_name] = expected in str(actual) if actual is not None else False
            elif op == "!~":
                env[var_name] = expected not in str(actual) if actual is not None else True
        try:
            return eval(expr_str, {}, env)
        except Exception:
            return False

    return matcher

def matches_filter(data: dict, filter_str: str) -> bool:
    if not filter_str:
        return True
    try:
        matcher = expr_to_lambda(filter_str)
        return matcher(data)
    except Exception:
        return False

# --- Endpoints ---

@app.get("/anchors")
def list_anchors(filter: List[str] = Query(default=[])):
    anchors = []
    for file in ANCHORS_DIR.glob("*.json"):
        try:
            with open(file) as f:
                data = json.load(f)

            matched = True
            for f_expr in filter:
                if not matches_filter(data, f_expr):
                    matched = False
                    break

            if matched:
                anchors.append(file.stem)

        except Exception:
            continue
    return anchors


@app.get("/anchors/{name}")
def get_anchor(name: str):
    file_path = ANCHORS_DIR / f"{name}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Anchor not found")
    return FileResponse(file_path)


@app.post("/anchors/_upload")
def upload_anchor(file: UploadFile = File(...)):
    try:
        data = json.load(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    if "type" not in data:
        raise HTTPException(status_code=400, detail="Anchor missing required 'type' field")

    anchor_name = data.get("name") or data.get("id") or file.filename.rsplit(".", 1)[0]
    if not re.match(r"^[a-zA-Z0-9_\-]+$", anchor_name):
        raise HTTPException(status_code=400, detail="Invalid or missing anchor name")

    dst = ANCHORS_DIR / f"{anchor_name}.json"
    try:
        with open(dst, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {e}")

    return {
        "status": "ok",
        "saved_as": str(dst),
        "anchor_name": anchor_name,
        "last_updated": data["last_updated"]
    }

@app.delete("/anchors/{name}")
def delete_anchor(name: str):
    path = ANCHORS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        return {"status": "deleted"}
    else:
        raise HTTPException(status_code=404, detail="Anchor not found")


@app.get("/anchors/{name}/raw")
def get_anchor_raw(name: str):
    file_path = ANCHORS_DIR / f"{name}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Anchor not found")
    try:
        with open(file_path) as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON or read error: {e}")


@app.get("/files/{filename}")
def download_file(filename: str):
    file_path = EXTERNAL_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@app.post("/files/upload")
def upload_external_file(file: UploadFile = File(...)):
    dest_path = EXTERNAL_DIR / file.filename
    try:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {
            "status": "ok",
            "filename": file.filename,
            "path": f"/files/{file.filename}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
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

        except Exception:
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
