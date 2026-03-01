from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # MongoDB — required
    MONGO_URI: str
    MONGO_DB: str

    # JWT — required
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # Vault encryption — required (base64-encoded 32 bytes)
    VAULT_MASTER_KEY: str

    # LDAP — optional (LDAP auth disabled if LDAP_SERVER is not set)
    LDAP_SERVER: Optional[str] = None
    LDAP_BASE_DN: Optional[str] = None
    LDAP_ADMIN_DN: Optional[str] = None
    LDAP_ADMIN_PASSWORD: Optional[str] = None
    LDAP_AUTH_ENABLED: bool = False

    # Local auth (MongoDB users collection)
    LOCAL_AUTH_ENABLED: bool = True

    # Timezone for timestamps
    TZ: str = "Europe/Madrid"

    # SPA knock listener — overrides WireGuard integration knock_port when set
    # VPN_KNOCK_PORT=0 (default) defers to the WireGuard integration config
    VPN_KNOCK_HOST: str = "0.0.0.0"
    VPN_KNOCK_PORT: int = 0

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def ldap_enabled(self) -> bool:
        return bool(self.LDAP_SERVER) and self.LDAP_AUTH_ENABLED


settings = Settings()
