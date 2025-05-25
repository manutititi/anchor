# core/logger.py

from typing import Optional, Dict, Any
from fastapi import Request, Response
from code.core.utils import now_tz
from code.core.ancdb import ancDB


class LogEntry:
    def __init__(
        self,
        *,
        resource: str,
        resource_id: str,
        action: str,
        user: str,
        ip: str,
        success: bool,
        status_code: int,
        extra: Optional[Dict[str, Any]] = None
    ):
        self.timestamp = now_tz()
        self.resource = resource
        self.resource_id = resource_id
        self.action = action
        self.user = user
        self.ip = ip
        self.success = success
        self.status_code = status_code
        self.extra = extra or {}

    def to_dict(self) -> Dict[str, Any]:
        base = {
            "timestamp": self.timestamp,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "action": self.action,
            "user": self.user,
            "ip": self.ip,
            "success": self.success,
            "status_code": self.status_code
        }
        # Añadir campos extra directamente al nivel raíz
        base.update(self.extra)
        return base

    def save(self, collection):
        collection.insert_one(self.to_dict())

    def save_default(self):
        self.save(ancDB().get_collection("log"))

    @classmethod
    def from_request(
        cls,
        *,
        request: Request,
        response: Response,
        resource: str,
        resource_id: str,
        action: str,
        success: bool,
        extra: Optional[Dict[str, Any]] = None
    ) -> "LogEntry":
        ip = request.headers.get("x-forwarded-for", request.client.host)
        return cls(
            resource=resource,
            resource_id=resource_id,
            action=action,
            user=request.state.user,
            ip=ip,
            success=success,
            status_code=response.status_code,
            extra=extra
        )
