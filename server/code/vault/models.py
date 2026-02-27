from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class SecretCreate(BaseModel):
    id: str
    plaintext: str
    description: str
    groups: list[str] = []
    users: list[str] = []
    allow_group_edit: bool = True
    expires_at: Optional[datetime] = None
    metadata: dict = {}


class SecretUpdate(BaseModel):
    plaintext: Optional[str] = None
    description: Optional[str] = None
    groups: Optional[list[str]] = None
    users: Optional[list[str]] = None
    allow_group_edit: Optional[bool] = None
    metadata: Optional[dict] = None
    transfer_to: Optional[str] = None  # reassign ownership to another user


class SecretInfo(BaseModel):
    id: str
    description: str
    version: int
    created_by: str
    created_at: str
    last_updated: str
    expires_at: Optional[str]
    owned: bool
