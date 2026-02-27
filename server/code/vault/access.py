def is_visible(secret: dict, user: str, groups: list[str], scopes: list[str] = []) -> bool:
    """Determine if a user/token can read a secret.

    Access model:
    - JWT users: creator always wins, then user allowlist, then group membership.
    - Service tokens: vault:read scope grants access to all secrets (scope IS the
      authorization). admin scope also grants full access.
      To restrict a secret to specific tokens, add the token name to `users`.
    """
    # Creator always has access
    if user == secret.get("created_by"):
        return True

    # Service tokens — the scope is the primary authorization mechanism
    if scopes:
        if "admin" in scopes:
            return True
        if "vault:read" in scopes:
            # Respect explicit user allowlist; otherwise the scope grants access
            if secret.get("users"):
                return user in secret["users"]
            return True
        return False  # service token without vault:read or admin cannot read

    # JWT users — user allowlist takes priority over groups
    if secret.get("users"):
        return user in secret["users"]

    # Group-based access (empty groups = creator-only, already handled above)
    return any(group in secret.get("groups", []) for group in groups)


def can_read_plaintext(secret: dict, user: str, groups: list[str], scopes: list[str] = []) -> bool:
    """Determine if a user/token may receive the decrypted plaintext of a secret.

    Stricter than is_visible(): admin scope does NOT grant plaintext access.
    Only the creator, explicitly listed users, group members, or a service token
    with vault:read scope (respecting the users allowlist) may decrypt.
    """
    if user == secret.get("created_by"):
        return True

    # Service tokens: vault:read grants access; admin does NOT override plaintext
    if scopes:
        if "vault:read" in scopes:
            if secret.get("users"):
                return user in secret["users"]
            return any(group in secret.get("groups", []) for group in groups)
        return False

    if secret.get("users"):
        return user in secret["users"]
    return any(group in secret.get("groups", []) for group in groups)


def can_edit(secret: dict, user: str, groups: list[str], scopes: list[str] = []) -> bool:
    """Determine if a user/token can update a secret."""
    if "admin" in scopes or "vault:write" in scopes:
        return True
    if secret.get("created_by") == user:
        return True
    if not secret.get("allow_group_edit", True):
        return False
    if secret.get("users"):
        return user in secret["users"]
    return any(group in secret.get("groups", []) for group in groups)


def can_delete(secret: dict, user: str, scopes: list[str] = []) -> bool:
    """Only the creator or an admin-scoped token can delete a secret."""
    if "admin" in scopes:
        return True
    return secret.get("created_by") == user
