"""Tenant settings service — persisted per section with typed defaults."""

from __future__ import annotations

import uuid
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.permissions import Role
from app.models import Tenant, User
from app.repositories import DocumentRepository, UserRepository
from app.repositories.settings_repo import SettingsRepository
from app.schemas.settings import (
    InvoiceOut,
    SettingsAI,
    SettingsBilling,
    SettingsGeneral,
    SettingsNotifications,
    SettingsSecurity,
)
from app.services.audit_service import AuditService

SectionModel = TypeVar("SectionModel")

SECTIONS: dict[str, type] = {
    "general": SettingsGeneral,
    "security": SettingsSecurity,
    "ai": SettingsAI,
    "notifications": SettingsNotifications,
    "billing": SettingsBilling,
}


class SettingsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = SettingsRepository(db)
        self.audit = AuditService(db)

    async def get_section(self, *, tenant: Tenant, section: str) -> SectionModel:
        model_cls = SECTIONS[section]
        row = await self.repository.get(tenant.id, section)
        stored = dict(row.data) if row else {}
        merged: dict = model_cls().model_dump()

        if section == "general":
            merged["organization_name"] = tenant.name
        elif section == "billing":
            merged["seats_used"] = await UserRepository(self.db).member_count(tenant.id)
            size = await DocumentRepository(self.db).total_size(tenant.id)
            merged["storage_used_gb"] = round(size / 1024**3, 2)

        merged.update(stored)
        if section == "general":
            merged["organization_name"] = tenant.name
        elif section == "billing":
            # live values always win over anything stored
            merged["seats_used"] = await UserRepository(self.db).member_count(tenant.id)
            size = await DocumentRepository(self.db).total_size(tenant.id)
            merged["storage_used_gb"] = round(size / 1024**3, 2)

        return model_cls(**merged)

    async def save_section(
        self,
        *,
        tenant: Tenant,
        user: User,
        section: str,
        payload: SectionModel,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SectionModel:
        if section == "general":
            general: SettingsGeneral = payload  # type: ignore[assignment]
            if general.default_collection_id:
                from app.repositories import CollectionRepository

                collection = await CollectionRepository(self.db).get(
                    tenant.id, uuid.UUID(general.default_collection_id)
                )
                if collection is None:
                    raise NotFoundError("COLLECTION_NOT_FOUND")
            if general.organization_name:
                tenant.name = general.organization_name

        data = payload.model_dump()
        if section == "billing":
            # never persist server-computed usage numbers
            data.pop("seats_used", None)
            data.pop("storage_used_gb", None)

        await self.repository.upsert(tenant.id, section, data)
        await self.audit.log(
            user=user,
            tenant=tenant,
            action="SETTINGS_UPDATED",
            resource_type="settings",
            resource_id=section,
            resource_label=section,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"section": section},
        )
        await self.db.commit()
        return payload

    async def invoices(self) -> list[InvoiceOut]:
        # No billing engine yet — the endpoint exists so the frontend contract
        # is satisfied and renders its empty state honestly.
        return []


__all__ = ["Role", "SECTIONS", "SettingsService"]
