from pydantic import BaseModel
from typing import Any, Optional


class TestResult(BaseModel):
    ok: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    details: dict[str, Any] = {}


class IntegrationSummary(BaseModel):
    type: str
    enabled: bool
    configured: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None
