from typing import Optional
from pydantic import BaseModel


class LeaseInfo(BaseModel):
    uid: str
    pubkey: str
    assigned_ip: str
    peer_name: str
    expires_at: str
    created_at: str
    vault_path: str


class VPNRequestBody(BaseModel):
    pubkey: str
    peer_name: Optional[str] = None


class VPNConfigResponse(BaseModel):
    assigned_ip: str
    server_pubkey: str
    server_endpoint: str
    lease_expires: str
    vault_path: str
    wg_conf_partial: str
