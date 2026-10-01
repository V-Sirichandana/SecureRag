"""Tenant routes — organization info and switching."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentTenant, CurrentUser, DbSession, require_role
from app.core.permissions import Role
from app.schemas.auth import OrganizationOut
from app.schemas.tenant import TenantOut, TenantUpdateIn
from app.services import tenant_service

tenants_router = APIRouter(prefix="/tenants", tags=["Tenants"])


@tenants_router.get(
    "",
    response_model=list[OrganizationOut],
    summary="Organizations the current user belongs to",
)
async def list_my_tenants(user: CurrentUser, db: DbSession) -> list[OrganizationOut]:
    return await tenant_service.list_organizations(db, user)


@tenants_router.get("/current", response_model=TenantOut, summary="Active organization")
async def current_tenant(tenant: CurrentTenant) -> TenantOut:
    return TenantOut(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        plan=tenant.plan,
        created_at=tenant.created_at,
    )


@tenants_router.patch(
    "/current",
    response_model=TenantOut,
    summary="Rename the active organization",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def update_current_tenant(
    payload: TenantUpdateIn,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> TenantOut:
    if not payload.name:
        return TenantOut(
            id=str(tenant.id),
            name=tenant.name,
            slug=tenant.slug,
            plan=tenant.plan,
            created_at=tenant.created_at,
        )
    updated = await tenant_service.rename_tenant(
        db, tenant=tenant, user=user, name=payload.name
    )
    return TenantOut(
        id=str(updated.id),
        name=updated.name,
        slug=updated.slug,
        plan=updated.plan,
        created_at=updated.created_at,
    )
