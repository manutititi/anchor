"""
LDAP auth shim — delegates to integrations/ldap/provider.py.

This module keeps its original public interface (ldap_authenticate, get_user_groups)
so auth/router.py requires no changes.
"""
from fastapi import HTTPException
from integrations.ldap.provider import LDAPProvider

_provider = LDAPProvider()


def _check_enabled():
    if not _provider.is_enabled():
        raise HTTPException(status_code=400, detail="LDAP authentication is not enabled")


def ldap_authenticate(username: str, password: str) -> bool:
    _check_enabled()
    return _provider.authenticate(username, password)


def get_user_groups(username: str) -> list[str]:
    _check_enabled()
    return _provider.get_groups(username)
