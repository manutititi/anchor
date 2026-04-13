"""
Pydantic models for all anchor types.

All models use extra="allow" so unknown fields from the server are preserved
transparently (forward-compatibility).
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Shared sub-objects
# ---------------------------------------------------------------------------

class GitCommit(_Base):
    hash: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    message: Optional[str] = None


class GitInfo(_Base):
    root: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[GitCommit] = None
    is_dirty: bool = False


class DockerInfo(_Base):
    active: bool = False
    services: list[str] = []


class SshPath(_Base):
    path: str
    comment: Optional[str] = None


# ---------------------------------------------------------------------------
# Anchor models
# ---------------------------------------------------------------------------

class BaseAnchor(_Base):
    name: str
    type: str
    groups: list[str] = []
    created_at: Optional[str] = None
    note: Optional[str] = None
    meta: dict[str, Any] = {}


class LocalAnchor(BaseAnchor):
    type: Literal["local"] = "local"
    path: str
    git: Optional[GitInfo] = None
    docker: Optional[DockerInfo] = None


class SshAnchor(BaseAnchor):
    type: Literal["ssh"] = "ssh"
    host: str
    user: str
    port: int = 22
    key: Optional[str] = None
    password: Optional[str] = None
    paths: list[SshPath] = []


class UrlAnchor(BaseAnchor):
    type: Literal["url"] = "url"
    base_url: str
    routes: list[dict[str, Any]] = []


class EnvAnchor(BaseAnchor):
    type: Literal["env"] = "env"
    path: str


class FilesAnchor(BaseAnchor):
    type: Literal["files"] = "files"
    files: list[dict[str, Any]] = []


class WorkflowAnchor(BaseAnchor):
    type: Literal["workflow"] = "workflow"
    steps: list[dict[str, Any]] = []


class AnsibleAnchor(BaseAnchor):
    type: Literal["ansible"] = "ansible"
    tasks: list[dict[str, Any]] = []


class DockerAnchor(BaseAnchor):
    type: Literal["docker"] = "docker"


class LdapAnchor(BaseAnchor):
    type: Literal["ldap"] = "ldap"
    host: str
    base_dn: Optional[str] = None
    bind_dn: Optional[str] = None


class MaskRule(_Base):
    pattern: str
    placeholder: str


class MaskAnchor(BaseAnchor):
    type: Literal["mask"] = "mask"
    rules: list[MaskRule] = []
    builtin: list[str] = []


class GenericAnchor(BaseAnchor):
    """Fallback for unknown anchor types."""


_TYPE_MAP: dict[str, type[BaseAnchor]] = {
    "local": LocalAnchor,
    "ssh": SshAnchor,
    "url": UrlAnchor,
    "env": EnvAnchor,
    "files": FilesAnchor,
    "workflow": WorkflowAnchor,
    "ansible": AnsibleAnchor,
    "docker": DockerAnchor,
    "ldap": LdapAnchor,
    "mask": MaskAnchor,
}


def parse_anchor(data: dict) -> BaseAnchor:
    """Deserialize a raw dict into the appropriate anchor model."""
    cls = _TYPE_MAP.get(data.get("type", ""), GenericAnchor)
    return cls.model_validate(data)
