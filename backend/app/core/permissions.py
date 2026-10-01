"""Role based access control.

Roles are stored uppercase in the database (OWNER, ADMIN, ...) and serialized
to the frontend as lowercase (owner, admin, ...) — the API accepts both.
Authorization decisions are centralized here so route handlers never duplicate
role checks.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.exceptions import AppError


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"

    @classmethod
    def from_value(cls, value: str) -> Role:
        """Parse a role from either case (``admin`` / ``ADMIN``)."""
        try:
            return cls(value.strip().upper())
        except (ValueError, AttributeError) as exc:
            raise AppError(
                "ROLE_INVALID",
                f"Unknown role: {value!r}. Expected one of "
                f"{', '.join(member.value for member in cls)}.",
                status_code=422,
            ) from exc


ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.MEMBER: 1,
    Role.MANAGER: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}


def role_at_least(role: Role | str, minimum: Role | str) -> bool:
    """Hierarchical check: OWNER satisfies ADMIN, ADMIN satisfies MANAGER, ..."""
    current = role if isinstance(role, Role) else Role.from_value(role)
    required = minimum if isinstance(minimum, Role) else Role.from_value(minimum)
    return ROLE_RANK[current] >= ROLE_RANK[required]


# Granular permission matrix (mirrors the frontend PermissionMatrix keys).
PERMISSIONS: dict[str, set[Role]] = {
    "view_documents": {Role.OWNER, Role.ADMIN, Role.MANAGER, Role.MEMBER, Role.VIEWER},
    "upload_documents": {Role.OWNER, Role.ADMIN, Role.MANAGER, Role.MEMBER},
    "delete_documents": {Role.OWNER, Role.ADMIN, Role.MANAGER},
    "manage_users": {Role.OWNER, Role.ADMIN},
    "manage_roles": {Role.OWNER, Role.ADMIN},
    "view_audit_logs": {Role.OWNER, Role.ADMIN},
    "manage_api_keys": {Role.OWNER, Role.ADMIN},
    "manage_ai_settings": {Role.OWNER, Role.ADMIN},
    # backend-specific granular checks (used by services)
    "manage_collections": {Role.OWNER, Role.ADMIN, Role.MANAGER},
    "use_chat": {Role.OWNER, Role.ADMIN, Role.MANAGER, Role.MEMBER, Role.VIEWER},
}


def has_permission(role: Role | str, permission: str) -> bool:
    current = role if isinstance(role, Role) else Role.from_value(role)
    allowed = PERMISSIONS.get(permission)
    if allowed is None:
        raise AppError(
            "FORBIDDEN",
            f"Unknown permission: {permission!r}.",
            status_code=500,
        )
    return current in allowed


def require_permission_value(role: Role | str, permission: str) -> None:
    if not has_permission(role, permission):
        raise AppError(
            "INSUFFICIENT_ROLE",
            f"This action requires a role with the '{permission}' permission.",
            status_code=403,
        )
