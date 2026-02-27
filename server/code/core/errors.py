from pydantic import BaseModel
from typing import Optional


class ErrorDetail(BaseModel):
    detail: str
    reason: Optional[str] = None


class NotFoundError(ErrorDetail):
    detail: str = "Resource not found"


class AccessDeniedError(ErrorDetail):
    detail: str = "Access denied"


class ConflictError(ErrorDetail):
    detail: str = "Resource already exists"
