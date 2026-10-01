"""Authentication routes.

Exposed twice: canonical ``/api/v1/auth/*`` (spec) and root ``/auth/*`` so the
existing Next.js client works unchanged with ``NEXT_PUBLIC_API_URL=http://localhost:8000``.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.dependencies import (
    AppSettings,
    CurrentTenant,
    CurrentUser,
    DbSession,
    RefreshToken,
    clear_auth_cookies,
    client_context,
    set_auth_cookies,
    try_get_current_user,
)
from app.core.exceptions import AppError
from app.models import User
from app.schemas.auth import (
    AcceptInviteIn,
    ForgotPasswordIn,
    LoginIn,
    RegisterIn,
    SessionOut,
    TokenOut,
)
from app.schemas.common import OkResponse
from app.services import auth_service

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


def _cookie_tenant(session: SessionOut) -> UUID | None:
    return UUID(session.user.organization_id) if session.user.organization_id else None


@auth_router.post(
    "/register",
    response_model=SessionOut,
    status_code=201,
    summary="Create a user and their organization",
)
async def register(
    payload: RegisterIn,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> SessionOut:
    session = await auth_service.register(db, settings, payload)
    set_auth_cookies(
        response,
        settings,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        tenant_id=_cookie_tenant(session),
    )
    return session


@auth_router.post(
    "/signup",
    response_model=SessionOut,
    status_code=201,
    summary="Alias of /auth/register used by the frontend",
)
async def signup(
    payload: RegisterIn,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> SessionOut:
    session = await auth_service.register(db, settings, payload)
    set_auth_cookies(
        response,
        settings,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        tenant_id=_cookie_tenant(session),
    )
    return session


@auth_router.post("/login", response_model=SessionOut, summary="Email + password login")
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> SessionOut:
    ip_address, user_agent = client_context(request)
    limiter = request.app.state.rate_limiter
    rate_key = f"{ip_address}:{payload.email.lower()}"
    await limiter.check(rate_key)
    session = await auth_service.login(
        db, settings, payload, ip_address=ip_address, user_agent=user_agent
    )
    await limiter.reset(rate_key)
    set_auth_cookies(
        response,
        settings,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        tenant_id=_cookie_tenant(session),
    )
    return session


@auth_router.post("/refresh", response_model=TokenOut, summary="Rotate the access token")
async def refresh(
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    token: RefreshToken,
) -> TokenOut:
    result = await auth_service.refresh(db, settings, token)
    set_auth_cookies(
        response,
        settings,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
    )
    return result


@auth_router.get("/me", response_model=SessionOut, summary="Current session")
async def me(
    user: CurrentUser,
    tenant: CurrentTenant,
    db: DbSession,
    settings: AppSettings,
) -> SessionOut:
    return await auth_service.build_session(db, user, settings, tenant)


@auth_router.post("/logout", status_code=204, summary="Clear the session cookies")
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    user: Annotated[User | None, Depends(try_get_current_user)] = None,
) -> Response:
    ip_address, user_agent = client_context(request)
    await auth_service.logout(db, user, ip_address=ip_address, user_agent=user_agent)
    clear_auth_cookies(response, settings)
    response.status_code = 204
    return response


@auth_router.post(
    "/accept-invite",
    response_model=SessionOut,
    summary="Accept an invitation and set the first password",
)
async def accept_invite(
    payload: AcceptInviteIn,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> SessionOut:
    """Exchanged by the invitee (no account yet) for a live session."""
    ip_address, user_agent = client_context(request)
    session = await auth_service.accept_invite(
        db, settings, payload, ip_address=ip_address, user_agent=user_agent
    )
    set_auth_cookies(
        response,
        settings,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        tenant_id=_cookie_tenant(session),
    )
    return session


@auth_router.post(
    "/forgot-password",
    response_model=OkResponse,
    summary="Request a password reset (no email provider yet)",
)
async def forgot_password(payload: ForgotPasswordIn) -> OkResponse:
    # Always report success — never reveal whether an account exists.
    return OkResponse()


@auth_router.post(
    "/oauth/{provider}",
    status_code=501,
    summary="Social sign-in (not configured yet)",
)
async def oauth(provider: Literal["google", "microsoft"]) -> None:
    raise AppError(
        "OAUTH_NOT_CONFIGURED",
        f"Sign-in with {provider} is not configured yet.",
        status_code=501,
    )
