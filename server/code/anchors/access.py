def is_visible(anchor: dict, user: str, groups: list[str], scopes: list[str] = []) -> bool:
    """Determine if a user/token can see an anchor.

    Access model (mirrors vault/access.py, but empty groups = all authenticated):
    - Creator always wins.
    - Service tokens: anchors:read or admin scope grants access.
    - JWT users: explicit user allowlist takes priority over groups.
    - Empty groups = all authenticated users (no restriction).
    """
    if user == anchor.get("created_by"):
        return True

    if scopes:
        if "admin" in scopes:
            return True
        if "anchors:read" in scopes:
            if anchor.get("users"):
                return user in anchor["users"]
            anchor_groups = anchor.get("groups", [])
            if not anchor_groups:
                return True
            return any(g in anchor_groups for g in groups)
        return False

    # JWT users — explicit user allowlist takes priority over groups
    if anchor.get("users"):
        return user in anchor["users"]

    anchor_groups = anchor.get("groups", [])
    if not anchor_groups:
        return True  # empty groups = all authenticated users
    return any(g in anchor_groups for g in groups)


def can_edit(anchor: dict, user: str, groups: list[str], scopes: list[str] = []) -> bool:
    """Can change non-ACL fields (note, host, paths, etc.)"""
    if user == anchor.get("created_by"):
        return True
    if scopes and ("admin" in scopes or "anchors:write" in scopes):
        return True
    if not anchor.get("allow_group_edit", False):
        return False
    if anchor.get("users"):
        return user in anchor["users"]
    ag = anchor.get("groups", [])
    return not ag or any(g in ag for g in groups)


def can_manage_acl(anchor: dict, user: str, groups: list[str], scopes: list[str] = []) -> bool:
    """Only creator, admin scope, or 'admins' group can change ACL fields."""
    if user == anchor.get("created_by"):
        return True
    if scopes and "admin" in scopes:
        return True
    return "admins" in groups


def can_delete(anchor: dict, user: str, groups: list[str], scopes: list[str] = []) -> bool:
    """Only creator, admin scope, or 'admins' group can delete an anchor."""
    if user == anchor.get("created_by"):
        return True
    if scopes and "admin" in scopes:
        return True
    return "admins" in groups
