from pydantic import BaseModel
from typing import Optional, Any


class AnchorUpsert(BaseModel):
    name: str
    type: str
    groups: list[str] = []
    model_config = {"extra": "allow"}
