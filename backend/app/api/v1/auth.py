"""Authentication routes.

Exposed twice: canonical ``/api/v1/auth/*`` (spec) and root ``/auth/*`` so the
existing Next.js client works unchanged with ``NEXT_PUBLIC_API_URL=http://localhost:8000``.
"""

from __future__ import annotations

import secrets
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
    ForgotPasswordOut,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    SessionOut,
    TokenOut,
)
from app.schemas.common import OkResponse
from app.services import auth_service, oauth_service

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
    response_model=ForgotPasswordOut,
    summary="Request a password reset link",
)
async def forgot_password(
    payload: ForgotPasswordIn,
    request: Request,
    db: DbSession,
    settings: AppSettings,
) -> ForgotPasswordOut:
    ip_address, _ = client_context(request)
    # Always report success — never reveal whether an account exists.
    token = await auth_service.request_password_reset(
        db, settings, payload.email, ip_address=ip_address
    )
    if token is not None:
        await auth_service.deliver_password_reset_email(settings, payload.email, token)
    out = ForgotPasswordOut(ok=True)
    if settings.debug and token is not None:
        out.reset_token = token
    return out


@auth_router.post(
    "/reset-password",
    response_model=OkResponse,
    summary="Consume a reset token and set a new password",
)
async def reset_password(
    payload: ResetPasswordIn,
    request: Request,
    db: DbSession,
    settings: AppSettings,
) -> OkResponse:
    ip_address, user_agent = client_context(request)
    await auth_service.reset_password(
        db, settings, payload.token, payload.new_password,
        ip_address=ip_address, user_agent=user_agent,
    )
    return OkResponse()


@auth_router.get(
    "/oauth/{provider}",
    summary="Start OAuth sign-in (redirects to provider)",
)
async def oauth_start(
    provider: Literal["google", "github"],
    request: Request,
    response: Response,
    settings: AppSettings,
) -> Response:
    if provider not in ("google", "github"):
        raise AppError("OAUTH_UNSUPPORTED", "Unsupported provider.", status_code=400)
    if not oauth_service.is_configured(settings, provider):
        raise AppError(
            "OAUTH_NOT_CONFIGURED",
            f"Sign-in with {provider} is not configured yet.",
            status_code=501,
        )
    state = secrets.token_urlsafe(24)
    # store state in a short-lived cookie for validation on callback
    response.set_cookie(
        key="oauth_state",
        value=state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.status_code = 302
    response.headers["Location"] = oauth_service.authorization_url(settings, provider, state)
    return response


@auth_router.get(
    "/oauth/{provider}/callback",
    summary="OAuth callback",
)
async def oauth_callback(
    provider: Literal["google", "github"],
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    if error:
        raise AppError(
            "OAUTH_DENIED",
            f"OAuth provider returned an error: {error}",
            status_code=400,
        )
    if not code or not state:
        raise AppError("OAUTH_INVALID_REQUEST", "Missing code or state.", status_code=400)
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        raise AppError("OAUTH_STATE_INVALID", "OAuth state validation failed.", status_code=400)
    if not oauth_service.is_configured(settings, provider):
        raise AppError(
            "OAUTH_NOT_CONFIGURED",
            f"Sign-in with {provider} is not configured.",
            status_code=501,
        )

    session = await oauth_service.oauth_login(db, settings, provider, code)
    set_auth_cookies(
        response,
        settings,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        tenant_id=_cookie_tenant(session),
    )
    # clear state cookie
    response.delete_cookie("oauth_state", path="/")
    frontend = settings.frontend_url or "http://localhost:3000"
    response.status_code = 302
    response.headers["Location"] = f"{frontend.rstrip('/')}/app/dashboard"
    return response
