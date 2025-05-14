from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pymongo.collection import Collection
from core.db_collection import get_mongo_collection

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    collection: Collection = get_mongo_collection("anchors")

    projection = {
        "_id": 0,
        "name": 1,
        "type": 1,
        "env": 1,
        "project": 1,
        "note": 1,
        "path": 1,
        "endpoint": 1,
        "last_updated": 1,
        "groups": 1,
        "external": 1
    }

    anchors = list(collection.find({}, projection))

    rows = []
    for anchor in anchors:
        name = anchor.get("name", "")
        type_ = anchor.get("type", "")
        env = anchor.get("env", "")
        project = anchor.get("project", "")
        note = anchor.get("note", "")
        updated = anchor.get("last_updated", "")
        groups = ", ".join(anchor.get("groups", [])) if anchor.get("groups") else "all"
        path_or_url = anchor.get("path") or anchor.get("endpoint", {}).get("base_url", "")
        external = "✅" if anchor.get("external") else ""

        row = f"""
            <tr>
                <td><a href="/anchors/{name}/raw" target="_blank">{name}</a></td>
                <td>{type_}</td>
                <td>{env}</td>
                <td>{project}</td>
                <td>{note}</td>
                <td>{groups}</td>
                <td>{external}</td>
                <td>{path_or_url}</td>
                <td>{updated}</td>
            </tr>
        """
        rows.append(row)

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
                    <th>Groups</th>
                    <th>External</th>
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
