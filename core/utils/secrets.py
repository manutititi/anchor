import re
import json
import requests
from pathlib import Path

# Cache en memoria para no repetir llamadas
_secret_cache = {}

def get_server_info():
    info_path = Path.home() / ".anchors" / "server" / "info.json"
    if not info_path.exists():
        raise RuntimeError("🔐 No remote server configured. Use: anc server url <url>")

    with open(info_path) as f:
        data = json.load(f)

    url = data.get("url")
    token = data.get("token")

    if not url or not token:
        raise RuntimeError("🔐 Missing server URL or token. Use `anc server auth`.")
    
    return url.rstrip("/"), token


def fetch_secret(ref_id):
    if not re.fullmatch(r"[a-zA-Z0-9_\-]+", ref_id):
        raise ValueError(f"Invalid secret ID: {ref_id}")
    
    if ref_id in _secret_cache:
        return _secret_cache[ref_id]

    server_url, token = get_server_info()
    url = f"{server_url}/ref/get/{ref_id}"

    try:
        res = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if res.status_code == 404:
            raise RuntimeError(f"🔐 Secret '{ref_id}' not found.")
        if res.status_code == 403:
            raise RuntimeError(f"🔐 Access denied to secret '{ref_id}'.")
        res.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"🔐 Connection error while fetching secret '{ref_id}': {e}")
    
    plaintext = res.json().get("plaintext", "")
    _secret_cache[ref_id] = plaintext
    return plaintext




def resolve_secrets(text: str) -> str:
    """
    Reemplaza [[secret:id]] o [[ secret:id ]] por su valor desde el servidor.
    Lanza error si queda algún marcador mal escrito sin resolver.
    """
    if not isinstance(text, str):
        return text

    # Acepta tanto [[secret:id]] como [[ secret:id ]]
    pattern = r"\[\[\s*secret\s*:\s*([a-zA-Z0-9_\-]+)\s*\]\]"
    matches = re.findall(pattern, text)

    for ref_id in set(matches):
        secret_value = fetch_secret(ref_id)
        text = re.sub(rf"\[\[\s*secret\s*:\s*{re.escape(ref_id)}\s*\]\]", secret_value, text)

    # Detectar cualquier marcador no válido que use [[...]] sin ser secret válido
    leftover = re.findall(r"\[\[\s*\w+\s*:[a-zA-Z0-9_\-]+\s*\]\]", text)
    if leftover:
        raise ValueError(f"❌ Invalid or unresolved secret marker(s): {leftover}")

    return text

