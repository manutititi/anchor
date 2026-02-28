from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from auth.middleware import get_current_user, get_current_groups
from integrations.registry import get_provider, all_providers
from integrations.store import (
    get_masked_config, get_metadata, get_config,
    save_config, delete_config, list_configs,
)

router = APIRouter()

ENCRYPTED_FIELDS: dict[str, list[str]] = {
    "ldap": ["admin_password"],
}


def _require_admin(
    user: str = Depends(get_current_user),
    groups: list[str] = Depends(get_current_groups),
) -> str:
    if "admins" not in groups:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("", tags=["integrations"])
def list_integrations(admin: str = Depends(_require_admin)):
    """List all known integration providers with their configuration status."""
    stored = {d["type"]: d for d in list_configs()}
    result = []
    for type_name, provider in all_providers().items():
        meta = stored.get(type_name, {})
        result.append({
            "type": type_name,
            "enabled": provider.is_enabled(),
            "configured": type_name in stored or provider.is_enabled(),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "created_by": meta.get("created_by"),
        })
    return JSONResponse(content=result)


@router.get("/{integration_type}", tags=["integrations"])
def get_integration(integration_type: str, admin: str = Depends(_require_admin)):
    """Get integration config (sensitive fields masked as ***)."""
    if not get_provider(integration_type):
        raise HTTPException(status_code=404, detail=f"Integration '{integration_type}' not found")
    config = get_masked_config(integration_type) or {}
    meta = get_metadata(integration_type) or {}
    provider = get_provider(integration_type)
    return JSONResponse(content={
        "type": integration_type,
        "enabled": provider.is_enabled(),
        "config": config,
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "created_by": meta.get("created_by"),
    })


@router.put("/{integration_type}", tags=["integrations"])
def upsert_integration(
    integration_type: str,
    body: dict[str, Any],
    admin: str = Depends(_require_admin),
):
    """
    Create or update integration configuration.
    Partial updates are supported — omitted fields keep their existing values.
    Sensitive fields sent as '***' are ignored (existing encrypted value is preserved).
    """
    provider = get_provider(integration_type)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Integration type '{integration_type}' not supported")

    enc_fields = ENCRYPTED_FIELDS.get(integration_type, [])

    # Merge incoming body with existing decrypted config
    existing = get_config(integration_type) or {}
    merged = {**existing, **body}

    # Preserve encrypted fields if the UI sent back masked "***"
    for field in enc_fields:
        if merged.get(field) == "***":
            merged[field] = existing.get(field, "")

    # Validate through the type-specific Pydantic model
    if integration_type == "ldap":
        from integrations.ldap.models import LDAPConfig
        try:
            LDAPConfig(**merged)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    save_config(integration_type, merged, enc_fields, admin)
    return JSONResponse(status_code=200, content={"detail": f"Integration '{integration_type}' saved."})


@router.delete("/{integration_type}", tags=["integrations"])
def remove_integration(integration_type: str, admin: str = Depends(_require_admin)):
    """Remove a stored integration configuration."""
    if not get_provider(integration_type):
        raise HTTPException(status_code=404, detail=f"Integration '{integration_type}' not found")
    if not delete_config(integration_type):
        raise HTTPException(status_code=404, detail=f"No stored config for '{integration_type}'")
    return JSONResponse(content={"detail": f"Integration '{integration_type}' removed."})


@router.post("/{integration_type}/test", tags=["integrations"])
def test_integration(integration_type: str, admin: str = Depends(_require_admin)):
    """Test connectivity to an integration. Uses current saved configuration."""
    provider = get_provider(integration_type)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Integration '{integration_type}' not found")
    result = provider.test_connection()
    return JSONResponse(content=result.model_dump())
