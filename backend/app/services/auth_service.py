"""Authentication service: register, login, refresh, session building.

Tenant access is NEVER taken from client input — a session's organizations are
built exclusively from the memberships stored in the database.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, ConflictError
from app.core.permissions import Role
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_invite_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import Membership, Tenant, User
from app.repositories import TenantRepository, UserRepository
from app.schemas.auth import (
    AcceptInviteIn,
    LoginIn,
    OrganizationOut,
    RegisterIn,
    SessionOut,
    SessionUser,
    TokenOut,
)
from app.services.audit_service import AuditService

DEFAULT_DEPARTMENT = "General"

# verified when the email is unknown so login timing does not reveal accounts
_DUMMY_HASH = hash_password(secrets.token_urlsafe(24))


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return (slug[:60] or "org").strip("-")


async def _unique_slug(repo: TenantRepository, base: str) -> str:
    candidate = base
    suffix = 2
    while await repo.slug_taken(candidate):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


async def build_session(
    db: AsyncSession,
    user: User,
    settings: Settings,
    tenant: Tenant | None = None,
) -> SessionOut:
    """Build the AuthSession payload + token pair from DB state only."""
    repo = UserRepository(db)
    memberships = await repo.memberships_with_tenants(user.id)

    active_membership, active_tenant = memberships[0] if memberships else (None, None)
    if tenant is not None:
        for membership, candidate in memberships:
            if candidate.id == tenant.id:
                active_membership, active_tenant = membership, candidate
                break

    organizations: list[OrganizationOut] = []
    for membership, candidate in memberships:
        organizations.append(
            OrganizationOut(
                id=str(candidate.id),
                name=candidate.name,
                plan=candidate.plan,
                member_count=await repo.member_count(candidate.id),
                role=membership.role.value.lower(),
                created_at=candidate.created_at,
            )
        )

    session_user = SessionUser(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=active_membership.role.value.lower() if active_membership else "viewer",
        department=user.department or DEFAULT_DEPARTMENT,
        organization_id=str(active_tenant.id) if active_tenant else "",
    )
    return SessionOut(
        access_token=create_access_token(user.id, settings),
        refresh_token=create_refresh_token(user.id, settings),
        user=session_user,
        organizations=organizations,
    )


async def register(
    db: AsyncSession,
    settings: Settings,
    payload: RegisterIn,
) -> SessionOut:
    """Create a user + their organization (user becomes OWNER)."""
    users = UserRepository(db)
    tenants = TenantRepository(db)

    if await users.get_by_email(payload.email):
        raise ConflictError("EMAIL_EXISTS", "An account with this email already exists.")

    tenant = Tenant(
        name=payload.organization_name,
        slug=await _unique_slug(tenants, slugify(payload.organization_name)),
    )
    await tenants.add(tenant)

    user = await users.add(
        User(
            email=payload.email.lower(),
            name=payload.name,
            password_hash=hash_password(payload.password),
            is_active=True,
            status="active",
            department=DEFAULT_DEPARTMENT,
        )
    )
    await users.add_membership(
        Membership(tenant_id=tenant.id, user_id=user.id, role=Role.OWNER)
    )
    await db.commit()
    return await build_session(db, user, settings, tenant)


async def login(
    db: AsyncSession,
    settings: Settings,
    payload: LoginIn,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> SessionOut:
    users = UserRepository(db)
    audit = AuditService(db)
    user = await users.get_by_email(payload.email)

    if user is None:
        verify_password(_DUMMY_HASH, payload.password)  # constant-ish timing
        await audit.log(
            user=None,
            tenant=None,
            action="LOGIN",
            resource_type="user",
            resource_label=payload.email,
            status="failure",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        raise AppError("INVALID_CREDENTIALS")

    if not verify_password(user.password_hash, payload.password):
        memberships = await users.memberships_with_tenants(user.id)
        await audit.log(
            user=user,
            tenant=memberships[0][1] if memberships else None,
            action="LOGIN",
            resource_type="user",
            resource_label=user.email,
            status="failure",
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"reason": "invalid_password"},
        )
        await db.commit()
        raise AppError("INVALID_CREDENTIALS")

    if not user.is_active:
        await db.commit()
        raise AppError("ACCOUNT_DISABLED")

    user.last_login_at = datetime.now(UTC)
    memberships = await users.memberships_with_tenants(user.id)
    tenant = memberships[0][1] if memberships else None
    await audit.log(
        user=user,
        tenant=tenant,
        action="LOGIN",
        resource_type="user",
        resource_id=user.id,
        resource_label=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return await build_session(db, user, settings, tenant)


async def accept_invite(
    db: AsyncSession,
    settings: Settings,
    payload: AcceptInviteIn,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> SessionOut:
    """Accept an invitation.

    Only a token minted for an account *created by that invitation* may set
    the first password, and only while its membership in the inviting
    organization still exists. Tokens for accounts that already existed never
    touch credentials — they just prove the invitee already has an account.
    """
    users = UserRepository(db)
    try:
        user_id, tenant_id, setup = decode_invite_token(payload.token, settings)
    except AppError as exc:
        if exc.code == "AUTH_TOKEN_EXPIRED":
            raise AppError("INVITE_EXPIRED") from exc
        raise AppError("INVITE_INVALID") from exc

    user = await users.get(user_id)
    if user is None:
        raise AppError("INVITE_INVALID")

    # the invitation only lives while its membership exists (revocation = delete)
    membership = await users.membership(user_id, tenant_id)
    if membership is None:
        raise AppError("INVITE_INVALID")

    if not setup:
        # C-1: the account predates this invitation — credentials are never
        # touched and no session is issued; the holder simply logs in.
        if user.is_active:
            raise ConflictError("INVITE_ALREADY_ACCEPTED")
        raise AppError("ACCOUNT_DISABLED")

    if user.is_active:
        # a setup token is single-use: it dies with the account it activates
        raise ConflictError("INVITE_ALREADY_ACCEPTED")

    user.password_hash = hash_password(payload.password)
    user.is_active = True
    user.status = "active"
    user.last_login_at = datetime.now(UTC)

    tenant = await TenantRepository(db).get(tenant_id)
    await AuditService(db).log(
        user=user,
        tenant=tenant,
        action="USER_ACTIVATED",
        resource_type="user",
        resource_id=user.id,
        resource_label=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"method": "invite"},
    )
    await db.commit()
    return await build_session(db, user, settings, tenant)


async def refresh(db: AsyncSession, settings: Settings, token: str | None) -> TokenOut:
    if not token:
        raise AppError("AUTH_REQUIRED", "A refresh token is required.")
    user_id = decode_token(token, settings, REFRESH_TOKEN_TYPE)
    user = await UserRepository(db).get(user_id)
    if user is None:
        raise AppError("AUTH_TOKEN_INVALID", "User no longer exists.")
    if not user.is_active:
        raise AppError("ACCOUNT_DISABLED")
    return TokenOut(
        access_token=create_access_token(user.id, settings),
        refresh_token=create_refresh_token(user.id, settings),
    )


async def logout(
    db: AsyncSession,
    user: User | None,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    if user is None:
        return
    users = UserRepository(db)
    memberships = await users.memberships_with_tenants(user.id)
    await AuditService(db).log(
        user=user,
        tenant=memberships[0][1] if memberships else None,
        action="LOGOUT",
        resource_type="user",
        resource_id=user.id,
        resource_label=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
