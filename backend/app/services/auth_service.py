"""Authentication service: register, login, refresh, session building.

Tenant access is NEVER taken from client input — a session's organizations are
built exclusively from the memberships stored in the database.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

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


async def request_password_reset(
    db: AsyncSession,
    settings: Settings,
    email: str,
    *,
    ip_address: str | None = None,
) -> str | None:
    """Mint a single-use, expiring reset token for the account (if it exists).

    Always performs the same work regardless of whether the email is known so
    timing does not reveal account existence. Returns the raw token when an
    account exists (caller is responsible for delivering it) and None otherwise.
    The stored value is only a hash, so a DB leak cannot be used to reset.
    """
    users = UserRepository(db)
    user = await users.get_by_email(email)
    if user is None:
        # Keep timing roughly consistent.
        hash_password(secrets.token_urlsafe(24))
        return None

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    user.password_reset_token_hash = token_hash
    user.password_reset_expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.password_reset_token_expire_minutes
    )
    await db.commit()
    return raw_token


async def reset_password(
    db: AsyncSession,
    settings: Settings,
    token: str,
    new_password: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Consume a reset token and set a new password.

    Single-use: the token is cleared on success. Expired or unknown tokens
    raise AUTH_TOKEN_INVALID (mapped to a generic message by the caller).
    """
    users = UserRepository(db)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    user = await users.get_by_password_reset_token_hash(token_hash)
    if user is None:
        raise AppError("AUTH_TOKEN_INVALID", "Reset link is invalid or has expired.")
    expires = user.password_reset_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires is None or expires < datetime.now(UTC):
        # clear expired token
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        await db.commit()
        raise AppError("AUTH_TOKEN_EXPIRED", "Reset link has expired.")
    if not user.is_active:
        raise AppError("ACCOUNT_DISABLED")

    user.password_hash = hash_password(new_password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    user.last_login_at = datetime.now(UTC)
    await db.commit()


async def deliver_password_reset_email(settings: Settings, email: str, token: str) -> None:
    """Send the reset link if SMTP is configured; otherwise log a warning.

    No paid service is required — the operator supplies their own SMTP server.
    """
    logger = logging.getLogger("securerag.auth")
    if not settings.smtp_host or not settings.smtp_from:
        logger.warning(
            "Password reset requested for %s but SMTP is not configured; "
            "reset token not delivered via email.",
            email,
        )
        return
    frontend_url = getattr(settings, "frontend_url", "")
    reset_url = (
        f"{frontend_url.rstrip('/')}/reset-password?token={token}"
        if frontend_url
        else None
    )
    body = (
        "You requested a password reset for your SecureRAG account.\n\n"
        + (
            f"Open this link to set a new password: {reset_url}\n\n"
            if reset_url
            else f"Your reset token is: {token}\n\n"
        )
        + f"This link expires in {settings.password_reset_token_expire_minutes} "
        "minutes. If you did not request this, you can ignore this email."
    )
    msg = EmailMessage()
    msg["Subject"] = "SecureRAG password reset"
    msg["From"] = settings.smtp_from
    msg["To"] = email
    msg.set_content(body)
    try:
        if settings.smtp_use_tls:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.starttls()
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send password reset email to %s: %s", email, type(exc).__name__)
