"""Tenant service — organization listing and renaming."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant, User
from app.repositories import UserRepository
from app.schemas.auth import OrganizationOut
from app.services.audit_service import AuditService


async def list_organizations(db: AsyncSession, user: User) -> list[OrganizationOut]:
    repo = UserRepository(db)
    memberships = await repo.memberships_with_tenants(user.id)
    organizations: list[OrganizationOut] = []
    for membership, tenant in memberships:
        organizations.append(
            OrganizationOut(
                id=str(tenant.id),
                name=tenant.name,
                plan=tenant.plan,
                member_count=await repo.member_count(tenant.id),
                role=membership.role.value.lower(),
                created_at=tenant.created_at,
            )
        )
    return organizations


async def rename_tenant(
    db: AsyncSession, *, tenant: Tenant, user: User, name: str
) -> Tenant:
    previous = tenant.name
    tenant.name = name
    await AuditService(db).log(
        user=user,
        tenant=tenant,
        action="TENANT_RENAMED",
        resource_type="tenant",
        resource_id=tenant.id,
        resource_label=name,
        metadata={"from": previous, "to": name},
    )
    await db.commit()
    return tenant
