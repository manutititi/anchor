from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
import shutil
import json

app = FastAPI()
ANCHORS_DIR = Path("anchors")
ANCHORS_DIR.mkdir(exist_ok=True)

@app.get("/anchors")
def list_anchors(filter: str = Query(default=None)):
    anchors = []
    for file in ANCHORS_DIR.glob("*.json"):
        try:
            with open(file) as f:
                data = json.load(f)
            if filter:
                key, value = filter.split("=", 1)
                if str(data.get(key)) != value:
                    continue
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

@app.post("/anchors/{name}")
def upload_anchor(name: str, file: UploadFile = File(...)):
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files allowed")
    dst = ANCHORS_DIR / f"{name}.json"
    with dst.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"status": "ok", "saved_as": str(dst)}

@app.delete("/anchors/{name}")
def delete_anchor(name: str):
    path = ANCHORS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        return {"status": "deleted"}
    else:
        raise HTTPException(status_code=404, detail="Anchor not found")

