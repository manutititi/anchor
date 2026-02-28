from pydantic import BaseModel, field_validator
from typing import Optional


class LDAPConfig(BaseModel):
    """
    Full LDAP/Active Directory integration configuration.

    Classic LDAP defaults:
        uid_attribute = "uid"

    Active Directory:
        uid_attribute = "sAMAccountName"
        server = "ldap://dc01.corp.local" or "ldaps://dc01.corp.local:636"
    """
    server: str                                  # ldap://host:389  or  ldaps://host:636
    base_dn: str                                 # dc=company,dc=com
    admin_dn: str                                # cn=admin,dc=company,dc=com
    admin_password: str                          # encrypted at rest

    user_search_base: str = "ou=users"           # relative to base_dn
    group_search_base: str = "ou=groups"         # relative to base_dn
    uid_attribute: str = "uid"                   # AD: sAMAccountName
    tls_verify: bool = True                      # False for self-signed certs
    timeout: int = 5
    enabled: bool = True
    sync_attributes: list[str] = ["mail", "displayName", "cn"]

    @field_validator("server")
    @classmethod
    def validate_server(cls, v: str) -> str:
        if not v.startswith(("ldap://", "ldaps://")):
            raise ValueError("server must start with ldap:// or ldaps://")
        return v.rstrip("/")
