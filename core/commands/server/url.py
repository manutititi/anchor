import json
from pathlib import Path
from core.utils.colors import green, red, dim

def run(args):
    url = args.value
    if not url:
        print(red("Missing server URL. Usage: anc server url http://your-server"))
        return

    if not url.startswith("http"):
        print(red("Invalid URL. Must start with http:// or https://"))
        return

    info_path = Path.home() / ".anchors" / "server" / "info.json"
    info_path.parent.mkdir(parents=True, exist_ok=True)

    if info_path.exists():
        with open(info_path) as f:
            current_data = json.load(f)
    else:
        current_data = {}

    current_data["url"] = url

    with open(info_path, "w") as f:
        json.dump(current_data, f, indent=2)

    print(green("Server URL configured successfully."))
    print(f"{dim('Saved to:')} {info_path}")
