from fastapi import Request, HTTPException

def check_anchor_access(anchor_data: dict, request: Request):
    """
    Lanza HTTP 403 si el usuario no pertenece a ningún grupo autorizado en el anchor.
    Si no hay grupos definidos en el anchor, no aplica restricciones.
    """
    allowed_groups = set(anchor_data.get("groups", []))
    user_groups = set(request.state.groups or [])

    if allowed_groups and not allowed_groups & user_groups:
        raise HTTPException(status_code=403, detail="Access denied: insufficient group permissions")
