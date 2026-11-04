"""OAuth (Google + GitHub) sign-in helpers."""
from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.permissions import Role
from app.core.security import hash_password
from app.models import Membership, Tenant, User
from app.repositories import TenantRepository, UserRepository
from app.schemas.auth import SessionOut
from app.services.auth_service import _unique_slug, build_session, slugify

logger = logging.getLogger("securerag.oauth")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


def is_configured(settings: Settings, provider: str) -> bool:
    if provider == "google":
        return bool(
            settings.google_client_id
            and settings.google_client_secret
            and settings.google_redirect_uri
        )
    if provider == "github":
        return bool(
            settings.github_client_id
            and settings.github_client_secret
            and settings.github_redirect_uri
        )
    return False


def authorization_url(settings: Settings, provider: str, state: str) -> str:
    if provider == "google":
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    if provider == "github":
        params = {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "scope": "user:email",
            "state": state,
        }
        return f"{GITHUB_AUTH_URL}?{urlencode(params)}"
    raise AppError(
        "OAUTH_UNSUPPORTED",
        f"Unsupported provider: {provider}",
        status_code=400,
    )


async def exchange_and_load_user(settings: Settings, provider: str, code: str) -> dict:
    """Exchange the authorization code and return a normalized user dict."""
    async with httpx.AsyncClient(timeout=20) as client:
        if provider == "google":
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if resp.status_code != 200:
                raise AppError(
                    "OAUTH_TOKEN_EXCHANGE_FAILED",
                    "Google token exchange failed.",
                    status_code=400,
                )
            tokens = resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                raise AppError(
                    "OAUTH_TOKEN_EXCHANGE_FAILED",
                    "Google did not return an access token.",
                    status_code=400,
                )
            info_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if info_resp.status_code != 200:
                raise AppError(
                    "OAUTH_USERINFO_FAILED",
                    "Failed to load Google profile.",
                    status_code=400,
                )
            info = info_resp.json()
            email = info.get("email")
            if not email or not info.get("email_verified", False):
                raise AppError(
                    "OAUTH_EMAIL_UNVERIFIED",
                    "Google account email is not verified.",
                    status_code=400,
                )
            return {
                "provider": "google",
                "provider_id": str(info.get("sub", "")),
                "email": email.lower(),
                "name": info.get("name") or email.split("@")[0],
            }

        if provider == "github":
            resp = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": settings.github_redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                raise AppError(
                    "OAUTH_TOKEN_EXCHANGE_FAILED",
                    "GitHub token exchange failed.",
                    status_code=400,
                )
            tokens = resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                raise AppError(
                    "OAUTH_TOKEN_EXCHANGE_FAILED",
                    "GitHub did not return an access token.",
                    status_code=400,
                )
            info_resp = await client.get(
                GITHUB_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if info_resp.status_code != 200:
                raise AppError(
                    "OAUTH_USERINFO_FAILED",
                    "Failed to load GitHub profile.",
                    status_code=400,
                )
            info = info_resp.json()
            email = info.get("email")
            if not email:
                # fetch verified primary email
                emails_resp = await client.get(
                    GITHUB_EMAILS_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                if emails_resp.status_code == 200:
                    emails = emails_resp.json() or []
                    primary = next(
                        (
                            e
                            for e in emails
                            if e.get("primary") and e.get("verified")
                        ),
                        None,
                    )
                    if primary:
                        email = primary.get("email")
            if not email:
                raise AppError(
                    "OAUTH_EMAIL_MISSING",
                    "GitHub account has no verified email.",
                    status_code=400,
                )
            return {
                "provider": "github",
                "provider_id": str(info.get("id", "")),
                "email": email.lower(),
                "name": info.get("name") or info.get("login") or email.split("@")[0],
            }

    raise AppError(
        "OAUTH_UNSUPPORTED",
        f"Unsupported provider: {provider}",
        status_code=400,
    )


async def oauth_login(
    db: AsyncSession,
    settings: Settings,
    provider: str,
    code: str,
) -> SessionOut:
    """Find or create the user for an OAuth identity and return a session."""
    profile = await exchange_and_load_user(settings, provider, code)

    users = UserRepository(db)
    tenants = TenantRepository(db)

    user = await users.get_by_email(profile["email"])
    if user is None:
        tenant = Tenant(
            name=f"{profile['name']}'s organization",
            slug=await _unique_slug(
                tenants, slugify(f"{profile['name']}'s organization")
            ),
        )
        await tenants.add(tenant)
        user = await users.add(
            User(
                email=profile["email"],
                name=profile["name"],
                password_hash=hash_password(secrets.token_urlsafe(32)),
                is_active=True,
                status="active",
                department="General",
            )
        )
        await users.add_membership(
            Membership(tenant_id=tenant.id, user_id=user.id, role=Role.OWNER)
        )
        await db.commit()
        return await build_session(db, user, settings, tenant)

    # existing user — ensure active
    if not user.is_active:
        user.is_active = True
        user.status = "active"
        await db.commit()
    memberships = await users.memberships_with_tenants(user.id)
    tenant = memberships[0][1] if memberships else None
    return await build_session(db, user, settings, tenant)
