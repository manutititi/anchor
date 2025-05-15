import os
import json

def load_server_info(path=None):
    path = path or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../server/info.json"))
    if not os.path.isfile(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)
