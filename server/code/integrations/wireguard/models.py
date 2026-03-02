from pydantic import BaseModel, field_validator


class WireGuardConfig(BaseModel):
    sidecar_url: str
    api_key: str = ""
    subnet: str = "10.13.13.0/24"
    server_endpoint: str = ""
    lease_hours: int = 8
    enabled: bool = True
    # SPA knock listener settings (0 = listener disabled)
    knock_port: int = 0
    server_vpn_uid: int = 1   # UID of the server itself (always subnet.1)

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

    # Networks routed through the tunnel (AllowedIPs in client config).
    # Default: 0.0.0.0/0 (full tunnel / all traffic).
    routes: list[str] = ["0.0.0.0/0"]

    # DNS servers pushed to clients in wg.conf. Empty = no DNS line.
    dns: list[str] = []

    @field_validator("knock_port")
    @classmethod
    def validate_knock_port(cls, v: int) -> int:
        if not (0 <= v <= 65535):
            raise ValueError("knock_port must be 0–65535 (0 = disabled)")
        return v

    @field_validator("routes")
    @classmethod
    def validate_routes(cls, v: list[str]) -> list[str]:
        import ipaddress
        for cidr in v:
            try:
                ipaddress.IPv4Network(cidr, strict=False)
            except ValueError:
                raise ValueError(f"Invalid CIDR: {cidr}")
        return v
