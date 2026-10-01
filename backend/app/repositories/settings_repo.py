"""Settings repository (one JSON row per tenant section)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TenantSettings


class SettingsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, tenant_id: uuid.UUID, section: str) -> TenantSettings | None:
        result = await self.db.execute(
            select(TenantSettings).where(
                TenantSettings.tenant_id == tenant_id,
                TenantSettings.section == section,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, tenant_id: uuid.UUID, section: str, data: dict
    ) -> TenantSettings:
        row = await self.get(tenant_id, section)
        if row is None:
            row = TenantSettings(tenant_id=tenant_id, section=section, data=data)
            self.db.add(row)
        else:
            row.data = data
        await self.db.flush()
        return row
