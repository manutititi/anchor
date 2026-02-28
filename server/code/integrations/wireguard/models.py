from pydantic import BaseModel, field_validator


class WireGuardConfig(BaseModel):
    sidecar_url: str
    api_key: str = ""
    subnet: str = "10.13.13.0/24"
    server_endpoint: str = ""
    lease_hours: int = 8
    enabled: bool = True

    @field_validator("sidecar_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("sidecar_url must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("lease_hours")
    @classmethod
    def validate_lease_hours(cls, v: int) -> int:
        if not (1 <= v <= 168):
            raise ValueError("lease_hours must be between 1 and 168 (1 week max)")
        return v
