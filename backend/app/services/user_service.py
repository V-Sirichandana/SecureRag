"""User management service — membership operations within one tenant."""

from __future__ import annotations

import re
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.permissions import Role, role_at_least
from app.core.security import create_invite_token, hash_password
from app.models import Membership, Tenant, User
from app.repositories import UserRepository
from app.schemas.user import InviteUserIn, InviteUserOut, UpdateUserIn, UserOut
from app.services.audit_service import AuditService


def serialize_user(user: User, membership: Membership) -> UserOut:
    return UserOut(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=membership.role.value.lower(),
        department=user.department or "General",
        status=user.status,  # type: ignore[arg-type]
        last_active=user.last_login_at or user.created_at,
        created_at=user.created_at,
    )


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UserRepository(db)
        self.audit = AuditService(db)

    # ----------------------------------------------------------------- reads
    async def list_users(self, *, tenant: Tenant) -> list[UserOut]:
        rows = await self.repository.members(tenant.id)
        return [serialize_user(user, membership) for membership, user in rows]

    async def get_membership(
        self, *, tenant: Tenant, user_id: uuid.UUID
    ) -> tuple[Membership, User]:
        membership = await self.repository.membership(user_id, tenant.id)
        if membership is None:
            raise NotFoundError("USER_NOT_FOUND")
        user = await self.repository.get(user_id)
        if user is None:
            raise NotFoundError("USER_NOT_FOUND")
        return membership, user

    # --------------------------------------------------------------- commands
    async def invite_user(
        self,
        *,
        tenant: Tenant,
        actor: User,
        actor_role: Role,
        payload: InviteUserIn,
        settings: Settings,
        ip_address: str | None,
        user_agent: str | None,
    ) -> InviteUserOut:
        requested_role = Role.from_value(payload.role)
        # H-1: only owners may hand out the owner role (checked before any write)
        if requested_role == Role.OWNER and not role_at_least(actor_role, Role.OWNER):
            raise AppError(
                "INSUFFICIENT_ROLE",
                "Only an owner can invite the owner role.",
                status_code=403,
            )
        email = payload.email.lower()
        existing = await self.repository.get_by_email(email)
        setup = existing is None
        if existing is not None:
            if await self.repository.membership(existing.id, tenant.id) is not None:
                raise ConflictError("EMAIL_EXISTS", "This user is already a member.")
            # C-1: never mutate the shared account here — deactivating it would
            # lock the user out of every other organization they belong to.
            user = existing
        else:
            user = await self.repository.add(
                User(
                    email=email,
                    name=_default_name(email),
                    # unusable hash until the invitee sets a password
                    password_hash=hash_password(secrets.token_urlsafe(32)),
                    is_active=False,
                    status="invited",
                    department=payload.department,
                )
            )

        membership = await self.repository.add_membership(
            Membership(tenant_id=tenant.id, user_id=user.id, role=requested_role)
        )
        await self.audit.log(
            user=actor,
            tenant=tenant,
            action="USER_INVITED",
            resource_type="user",
            resource_id=user.id,
            resource_label=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"role": membership.role.value, "department": payload.department},
        )
        await self.db.commit()
        # Stand-in for email delivery: non-production environments return the
        # acceptance token inline so the flow is usable before SMTP exists.
        invite_token = (
            None
            if settings.is_production
            else create_invite_token(user.id, tenant.id, settings, setup=setup)
        )
        return InviteUserOut.model_validate(
            {**serialize_user(user, membership).model_dump(), "invite_token": invite_token}
        )

    async def update_user(
        self,
        *,
        tenant: Tenant,
        actor: User,
        actor_role: Role,
        user_id: uuid.UUID,
        payload: UpdateUserIn,
        ip_address: str | None,
        user_agent: str | None,
    ) -> UserOut:
        if user_id == actor.id:
            raise AppError(
                "CANNOT_MODIFY_SELF",
                "You cannot change your own role or status.",
                status_code=403,
            )
        membership, user = await self.get_membership(tenant=tenant, user_id=user_id)
        # H-2: owners are immutable to anyone below owner rank
        if membership.role == Role.OWNER and not role_at_least(actor_role, Role.OWNER):
            raise AppError(
                "INSUFFICIENT_ROLE",
                "Only an owner can modify another owner.",
                status_code=403,
            )
        metadata: dict[str, str] = {}

        if payload.role is not None:
            target_role = Role.from_value(payload.role)
            if target_role == Role.OWNER and not role_at_least(actor_role, Role.OWNER):
                raise AppError(
                    "INSUFFICIENT_ROLE",
                    "Only an owner can grant the owner role.",
                    status_code=403,
                )
            if membership.role == Role.OWNER and target_role != Role.OWNER:
                await self._ensure_not_last_owner(tenant.id, user_id)
            changed = {"from": membership.role.value, "to": target_role.value}
            membership.role = target_role
            metadata.update(changed)

        if payload.status is not None:
            if payload.status != "active" and user_id in await self._active_owner_ids(tenant.id):
                await self._ensure_not_last_owner(tenant.id, user_id)
            user.status = payload.status
            user.is_active = payload.status == "active"
            metadata["status"] = payload.status

        await self.audit.log(
            user=actor,
            tenant=tenant,
            action="PERMISSION_CHANGED" if payload.role else "USER_UPDATED",
            resource_type="user",
            resource_id=user.id,
            resource_label=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata,
        )
        await self.db.commit()
        return serialize_user(user, membership)

    async def remove_user(
        self,
        *,
        tenant: Tenant,
        actor: User,
        actor_role: Role,
        user_id: uuid.UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        if user_id == actor.id:
            raise AppError(
                "CANNOT_MODIFY_SELF",
                "You cannot remove your own account from this organization.",
                status_code=403,
            )
        membership, user = await self.get_membership(tenant=tenant, user_id=user_id)
        # H-2: owners are immutable to anyone below owner rank
        if membership.role == Role.OWNER and not role_at_least(actor_role, Role.OWNER):
            raise AppError(
                "INSUFFICIENT_ROLE",
                "Only an owner can remove another owner.",
                status_code=403,
            )
        if membership.role == Role.OWNER:
            await self._ensure_not_last_owner(tenant.id, user_id)

        await self.repository.delete_membership(membership)

        # orphaned accounts (no tenant left) are deactivated
        remaining = await self.repository.memberships_with_tenants(user.id)
        if not remaining:
            user.is_active = False
            user.status = "disabled"

        await self.audit.log(
            user=actor,
            tenant=tenant,
            action="USER_REMOVED",
            resource_type="user",
            resource_id=user.id,
            resource_label=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"role": membership.role.value},
        )
        await self.db.commit()

    # --------------------------------------------------------------- helpers
    async def _ensure_not_last_owner(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        count = await self._owner_count(tenant_id)
        if count <= 1:
            raise ConflictError("LAST_OWNER", "The organization must keep at least one owner.")

    async def _owner_count(self, tenant_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(Membership.id)).where(
                Membership.tenant_id == tenant_id,
                Membership.role == Role.OWNER,
            )
        )
        return int(result.scalar_one())

    async def _active_owner_ids(self, tenant_id: uuid.UUID) -> set[uuid.UUID]:
        result = await self.db.execute(
            select(Membership.user_id).where(
                Membership.tenant_id == tenant_id,
                Membership.role == Role.OWNER,
            )
        )
        return set(result.scalars())


def _default_name(email: str) -> str:
    local = email.split("@")[0]
    words = [part for part in re.split(r"[._+\-]", local) if part]
    pretty = " ".join(word.capitalize() for word in words)
    return pretty or local
