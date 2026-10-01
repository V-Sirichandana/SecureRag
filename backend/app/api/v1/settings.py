"""Settings routes (frontend contract). Writes require ADMIN except notifications."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import (
    CurrentTenant,
    CurrentUser,
    DbSession,
    client_context,
    require_role,
)
from app.core.permissions import Role
from app.schemas.settings import (
    InvoiceOut,
    SettingsAI,
    SettingsBilling,
    SettingsGeneral,
    SettingsNotifications,
    SettingsSecurity,
)
from app.services.settings_service import SettingsService

settings_router = APIRouter(prefix="/settings", tags=["Settings"])

SectionName = Literal["general", "security", "ai", "notifications", "billing"]

_MODELS = {
    "general": SettingsGeneral,
    "security": SettingsSecurity,
    "ai": SettingsAI,
    "notifications": SettingsNotifications,
    "billing": SettingsBilling,
}


async def _get(section: SectionName, tenant: CurrentTenant, db: DbSession):
    return await SettingsService(db).get_section(tenant=tenant, section=section)


@settings_router.get("/general", response_model=SettingsGeneral, summary="General settings")
async def get_general(tenant: CurrentTenant, db: DbSession) -> SettingsGeneral:
    return await _get("general", tenant, db)  # type: ignore[return-value]


@settings_router.put(
    "/general",
    response_model=SettingsGeneral,
    summary="Save general settings",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def save_general(
    payload: SettingsGeneral,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> SettingsGeneral:
    ip_address, user_agent = client_context(request)
    return await SettingsService(db).save_section(  # type: ignore[return-value]
        tenant=tenant,
        user=user,
        section="general",
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@settings_router.get("/security", response_model=SettingsSecurity, summary="Security settings")
async def get_security(tenant: CurrentTenant, db: DbSession) -> SettingsSecurity:
    return await _get("security", tenant, db)  # type: ignore[return-value]


@settings_router.put(
    "/security",
    response_model=SettingsSecurity,
    summary="Save security settings",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def save_security(
    payload: SettingsSecurity,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> SettingsSecurity:
    ip_address, user_agent = client_context(request)
    return await SettingsService(db).save_section(  # type: ignore[return-value]
        tenant=tenant,
        user=user,
        section="security",
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@settings_router.get("/ai", response_model=SettingsAI, summary="AI settings")
async def get_ai(tenant: CurrentTenant, db: DbSession) -> SettingsAI:
    return await _get("ai", tenant, db)  # type: ignore[return-value]


@settings_router.put(
    "/ai",
    response_model=SettingsAI,
    summary="Save AI settings",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def save_ai(
    payload: SettingsAI,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> SettingsAI:
    ip_address, user_agent = client_context(request)
    return await SettingsService(db).save_section(  # type: ignore[return-value]
        tenant=tenant,
        user=user,
        section="ai",
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@settings_router.get(
    "/notifications", response_model=SettingsNotifications, summary="Notification settings"
)
async def get_notifications(tenant: CurrentTenant, db: DbSession) -> SettingsNotifications:
    return await _get("notifications", tenant, db)  # type: ignore[return-value]


@settings_router.put(
    "/notifications",
    response_model=SettingsNotifications,
    summary="Save notification settings",
)
async def save_notifications(
    payload: SettingsNotifications,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> SettingsNotifications:
    ip_address, user_agent = client_context(request)
    return await SettingsService(db).save_section(  # type: ignore[return-value]
        tenant=tenant,
        user=user,
        section="notifications",
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@settings_router.get("/billing", response_model=SettingsBilling, summary="Billing settings")
async def get_billing(tenant: CurrentTenant, db: DbSession) -> SettingsBilling:
    return await _get("billing", tenant, db)  # type: ignore[return-value]


@settings_router.put(
    "/billing",
    response_model=SettingsBilling,
    summary="Save billing settings",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def save_billing(
    payload: SettingsBilling,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> SettingsBilling:
    ip_address, user_agent = client_context(request)
    return await SettingsService(db).save_section(  # type: ignore[return-value]
        tenant=tenant,
        user=user,
        section="billing",
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@settings_router.get(
    "/billing/invoices",
    response_model=list[InvoiceOut],
    summary="Invoice history (empty until billing ships)",
)
async def invoices(tenant: CurrentTenant, db: DbSession) -> list[InvoiceOut]:
    return await SettingsService(db).invoices()


__all__ = ["settings_router", "SectionName", "_MODELS"]
