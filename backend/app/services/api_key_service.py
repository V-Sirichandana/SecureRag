"""API key service — generate, list and revoke keys (hashes only)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.security import generate_api_key, mask_api_key
from app.models import ApiKey, Tenant, User
from app.repositories.chat import ApiKeyRepository
from app.schemas.api_key import ApiKeyCreatedOut, ApiKeyCreateIn, ApiKeyOut
from app.services.audit_service import AuditService


def serialize_api_key(key: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=str(key.id),
        name=key.name,
        environment=key.environment,  # type: ignore[arg-type]
        masked_key=mask_api_key(key.environment),
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        expires_at=key.expires_at,
        permissions=key.permissions or [],
    )


class ApiKeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ApiKeyRepository(db)
        self.audit = AuditService(db)

    async def list_keys(self, *, tenant: Tenant) -> list[ApiKeyOut]:
        keys = await self.repository.list(tenant.id)
        return [serialize_api_key(key) for key in keys]

    async def create_key(
        self,
        *,
        tenant: Tenant,
        user: User,
        payload: ApiKeyCreateIn,
        ip_address: str | None,
        user_agent: str | None,
    ) -> ApiKeyCreatedOut:
        raw_key, key_hash = generate_api_key(payload.environment)
        expires_at = None
        if payload.expiration != "never":
            expires_at = datetime.now(UTC) + timedelta(days=int(payload.expiration))

        key = ApiKey(
            tenant_id=tenant.id,
            name=payload.name,
            key_hash=key_hash,
            environment=payload.environment,
            permissions=payload.permissions,
            expires_at=expires_at,
            created_by=user.id,
        )
        await self.repository.add(key)
        await self.audit.log(
            user=user,
            tenant=tenant,
            action="API_KEY_CREATED",
            resource_type="api_key",
            resource_id=key.id,
            resource_label=key.name,
            ip_address=ip_address,
            user_agent=user_agent,
            # the raw key is never logged
            metadata={"environment": payload.environment, "expires": payload.expiration},
        )
        await self.db.commit()
        return ApiKeyCreatedOut(key=serialize_api_key(key), plaintext=raw_key)

    async def revoke_key(
        self,
        *,
        tenant: Tenant,
        user: User,
        key_id: uuid.UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        key = await self.repository.get(tenant.id, key_id)
        if key is None:
            raise NotFoundError("API_KEY_NOT_FOUND")
        if key.revoked_at is None:
            key.revoked_at = datetime.now(UTC)
            await self.audit.log(
                user=user,
                tenant=tenant,
                action="API_KEY_REVOKED",
                resource_type="api_key",
                resource_id=key.id,
                resource_label=key.name,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"environment": key.environment},
            )
            await self.db.commit()

