"""Central audit logging.

Every important event is written through :meth:`AuditService.log`. The write
shares the caller's database transaction, so business data and its audit trail
commit atomically. Passwords, raw API keys and other secrets are never logged.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Tenant, User
from app.repositories import AuditRepository

# keys whose values must never reach the audit table
SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "new_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "key",
    "plaintext",
    "authorization",
    "cookie",
}


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    """Flatten to strings and drop anything that looks like a secret."""
    if not metadata:
        return {}
    clean: dict[str, str] = {}
    for key, value in metadata.items():
        if str(key).lower() in SENSITIVE_KEYS:
            continue
        clean[str(key)] = str(value)
    return clean


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = AuditRepository(db)

    async def log(
        self,
        *,
        user: User | None,
        tenant: Tenant | uuid.UUID | None,
        action: str,
        resource_type: str = "",
        resource_id: str | uuid.UUID | None = None,
        resource_label: str | None = None,
        status: str = "success",
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        tenant_id = tenant.id if isinstance(tenant, Tenant) else tenant
        entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user.id if user else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            resource_label=resource_label,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:512] or None,
            status=status,
            metadata_=sanitize_metadata(metadata),
        )
        return await self.repository.add(entry)
