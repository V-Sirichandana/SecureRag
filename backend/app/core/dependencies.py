"""Reusable FastAPI dependencies: database, principal, tenant, RBAC.

Resolution flow (never trusts client-supplied tenant ids for authorization)::

    JWT / session cookie
        → get_current_user()      (user from DB)
        → get_current_membership() (membership looked up in DB; an explicit
                                    X-Tenant-Id / cookie hint is *verified*
                                    against those memberships)
        → get_current_tenant()     (tenant row from the verified membership)
        → require_role() / require_permission()
        → tenant-scoped resource fetch
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, AuthenticationError, AuthorizationError
from app.core.permissions import Role, has_permission, role_at_least
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.models import Membership, Tenant, User
from app.repositories import UserRepository

ACCESS_COOKIE = "sr_access_token"
REFRESH_COOKIE = "sr_refresh_token"
TENANT_COOKIE = "sr_tenant"
TENANT_HEADER = "x-tenant-id"


@dataclass(frozen=True)
class CurrentContext:
    """Fully resolved request principal."""

    user: User
    membership: Membership
    tenant: Tenant

    @property
    def role(self) -> Role:
        return self.membership.role


# --------------------------------------------------------------------- database
async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


# ---------------------------------------------------------------------- tokens
def get_access_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """Bearer header first (API clients), then the HttpOnly session cookie."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


def get_refresh_token(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE)


AccessToken = Annotated[str | None, Depends(get_access_token)]
RefreshToken = Annotated[str | None, Depends(get_refresh_token)]


# ------------------------------------------------------------------- principal
async def get_current_user(
    request: Request,
    db: DbSession,
    token: AccessToken,
) -> User:
    cached = getattr(request.state, "user", None)
    if cached is not None:
        return cached
    if not token:
        raise AuthenticationError("AUTH_REQUIRED")
    settings = get_app_settings(request)
    user_id = decode_token(token, settings, ACCESS_TOKEN_TYPE)
    user = await UserRepository(db).get(user_id)
    if user is None:
        raise AuthenticationError("AUTH_TOKEN_INVALID", "This account no longer exists.")
    if not user.is_active:
        raise AuthorizationError("ACCOUNT_DISABLED")
    request.state.user = user
    return user


async def try_get_current_user(
    request: Request,
    db: DbSession,
    token: AccessToken,
) -> User | None:
    """Best-effort principal for optional auth (e.g. logout)."""
    try:
        return await get_current_user(request, db, token)
    except AppError:
        return None


async def get_current_membership(
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Membership:
    cached = getattr(request.state, "membership", None)
    if cached is not None:
        return cached

    memberships = await UserRepository(db).memberships_with_tenants(user.id)
    hint = request.headers.get(TENANT_HEADER) or request.cookies.get(TENANT_COOKIE)

    if hint:
        match = next(
            (
                (membership, tenant)
                for membership, tenant in memberships
                if str(tenant.id) == hint or tenant.slug == hint
            ),
            None,
        )
        if match is None:
            # explicit selection of an org the user does not belong to
            raise AuthorizationError(
                "TENANT_ACCESS_DENIED",
                "You are not a member of the requested organization.",
            )
    else:
        if not memberships:
            raise AuthorizationError(
                "NO_MEMBERSHIP",
                "This user does not belong to any organization yet.",
            )
        membership, tenant = memberships[0]
        match = (membership, tenant)

    membership, tenant = match
    request.state.membership = membership
    request.state.tenant = tenant
    return membership


async def get_current_tenant(
    request: Request,
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> Tenant:
    """Tenant derived from the verified membership (never from the client)."""
    return request.state.tenant


async def get_context(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> CurrentContext:
    tenant: Tenant = request.state.tenant
    return CurrentContext(user=user, membership=membership, tenant=tenant)


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentMembership = Annotated[Membership, Depends(get_current_membership)]
CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]
CurrentContextDep = Annotated[CurrentContext, Depends(get_context)]


# ------------------------------------------------------------------------ RBAC
def require_role(minimum: Role | str):
    """Dependency factory: reject callers below ``minimum`` (hierarchical)."""
    required = minimum if isinstance(minimum, Role) else Role.from_value(minimum)

    async def dependency(
        membership: CurrentMembership,
    ) -> Membership:
        if not role_at_least(membership.role, required):
            raise AuthorizationError(
                "INSUFFICIENT_ROLE",
                f"This action requires the {required.value} role or higher.",
            )
        return membership

    return dependency


def require_permission(permission: str):
    """Dependency factory using the centralized permission matrix."""

    async def dependency(membership: CurrentMembership) -> Membership:
        if not has_permission(membership.role, permission):
            raise AuthorizationError(
                "INSUFFICIENT_ROLE",
                f"This action requires the '{permission}' permission.",
            )
        return membership

    return dependency


# --------------------------------------------------------------------- cookies
def set_auth_cookies(
    response,
    settings: Settings,
    *,
    access_token: str,
    refresh_token: str,
    tenant_id: uuid.UUID | None = None,
) -> None:
    secure = settings.cookie_secure
    samesite = settings.cookie_samesite
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
        max_age=settings.access_token_expire_minutes * 60,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
        max_age=settings.refresh_token_expire_days * 86400,
    )
    if tenant_id is not None:
        response.set_cookie(
            TENANT_COOKIE,
            str(tenant_id),
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/",
            max_age=settings.refresh_token_expire_days * 86400,
        )


def clear_auth_cookies(response, settings: Settings) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, TENANT_COOKIE):
        response.delete_cookie(name, path="/", samesite=settings.cookie_samesite)


def client_context(request: Request) -> tuple[str | None, str | None]:
    """(ip_address, user_agent) for audit logging."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")
