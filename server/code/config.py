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

    # Port the Anchor server listens on — embedded in provision tokens so the
    # client knows where to call /auth/login and /vpn/promote over the tunnel
    VPN_SERVER_PORT: int = 17017

    # SPA V2 — X25519 keypair for ECDH-based knock encryption.
    # The client encrypts the SPA packet using the public key; the server
    # decrypts with the private key.  No shared secrets on the client side.
    # Generate:
    #   python -c "from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey; \
    #     import base64; k=X25519PrivateKey.generate(); \
    #     print('SPA_PRIVKEY=' + base64.b64encode(k.private_bytes_raw()).decode()); \
    #     print('SPA_PUBKEY=' + base64.b64encode(k.public_key().public_bytes_raw()).decode())"
    SPA_PRIVKEY: str = ""    # base64-encoded 32-byte X25519 private key
    SPA_PUBKEY: str = ""     # base64-encoded 32-byte X25519 public key (auto-derived if empty)

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def ldap_enabled(self) -> bool:
        return bool(self.LDAP_SERVER) and self.LDAP_AUTH_ENABLED


settings = Settings()
