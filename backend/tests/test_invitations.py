"""Invitation acceptance: invite -> set first password -> active member."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest_asyncio
from httpx import AsyncClient

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from tests.conftest import PASSWORD, auth, make_client

TEST_SECRET = "test-secret-key-not-for-production"


@pytest_asyncio.fixture
async def owner(actor_factory):
    return await actor_factory(name="Alice Owner", email="alice@example.com", org="Acme")


@pytest_asyncio.fixture
async def invitee(app) -> AsyncClient:
    async with make_client(app) as client:
        yield client


async def invite(
    owner_client: AsyncClient,
    session: dict,
    *,
    email: str = "mallory@example.com",
    role: str = "member",
) -> dict:
    response = await owner_client.post(
        "/users/invite",
        json={"email": email, "role": role, "department": "Engineering"},
        headers=auth(session),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_invite_returns_token_and_accept_activates_account(owner, invitee):
    owner_client, session = owner
    invited = await invite(owner_client, session)
    assert invited["status"] == "invited"
    assert invited["inviteToken"], "non-production invites must carry an acceptance token"

    accept = await invitee.post(
        "/auth/accept-invite",
        json={"token": invited["inviteToken"], "password": PASSWORD},
    )
    assert accept.status_code == 200, accept.text
    body = accept.json()
    assert body["user"]["email"] == "mallory@example.com"
    assert body["accessToken"]
    assert body["organizations"]

    # the new member can now authenticate with the password they chose
    logged = await invitee.post(
        "/auth/login", json={"email": "mallory@example.com", "password": PASSWORD}
    )
    assert logged.status_code == 200, logged.text
    assert logged.json()["user"]["email"] == "mallory@example.com"


async def test_invited_user_cannot_log_in_before_accepting(owner, invitee):
    owner_client, session = owner
    await invite(owner_client, session, email="pending@example.com")

    response = await invitee.post(
        "/auth/login", json={"email": "pending@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401


async def test_accept_invite_rejects_garbage_token(invitee):
    response = await invitee.post(
        "/auth/accept-invite",
        json={"token": "x" * 40, "password": PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVITE_INVALID"


async def test_accept_invite_rejects_access_token(owner, invitee):
    owner_client, session = owner
    await invite(owner_client, session, email="swap@example.com")

    response = await invitee.post(
        "/auth/accept-invite",
        json={"token": session["accessToken"], "password": PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVITE_INVALID"


async def test_invite_token_is_single_use(owner, invitee):
    owner_client, session = owner
    invited = await invite(owner_client, session, email="once@example.com")

    first = await invitee.post(
        "/auth/accept-invite",
        json={"token": invited["inviteToken"], "password": PASSWORD},
    )
    assert first.status_code == 200, first.text

    second = await invitee.post(
        "/auth/accept-invite",
        json={"token": invited["inviteToken"], "password": "another-pass-1"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "INVITE_ALREADY_ACCEPTED"


async def test_accept_invite_rejects_expired_token(owner, invitee):
    owner_client, session = owner
    invited = await invite(owner_client, session, email="late@example.com")

    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": invited["id"],
            "type": "invite",
            "jti": "test",
            "iat": now - timedelta(days=10),
            "exp": now - timedelta(days=3),
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    response = await invitee.post(
        "/auth/accept-invite", json={"token": expired, "password": PASSWORD}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVITE_EXPIRED"


async def test_accept_invite_requires_long_password(owner, invitee):
    owner_client, session = owner
    invited = await invite(owner_client, session, email="short@example.com")

    response = await invitee.post(
        "/auth/accept-invite",
        json={"token": invited["inviteToken"], "password": "short"},
    )
    assert response.status_code == 422


async def test_production_invite_never_returns_the_token():
    """In production the acceptance token is delivered out of band (email)."""
    settings = Settings(
        app_env="production",
        jwt_secret_key="prod-secret-key-for-tests-only-0123",
        database_url="sqlite+aiosqlite:///:memory:",
        cors_origins="http://localhost:3000",
    )
    application = create_app(settings)
    await create_all(application.state.engine)
    try:
        async with make_client(application) as client:
            registered = await client.post(
                "/auth/register",
                json={
                    "name": "Prod Owner",
                    "email": "prod@example.com",
                    "password": PASSWORD,
                    "organization_name": "Prod Org",
                },
            )
            assert registered.status_code == 201, registered.text
            session = registered.json()

            invited = await client.post(
                "/users/invite",
                json={"email": "prod-member@example.com", "role": "member", "department": "IT"},
                headers=auth(session),
            )
            assert invited.status_code == 201, invited.text
            assert invited.json().get("inviteToken") is None
    finally:
        await drop_all(application.state.engine)
        await application.state.engine.dispose()
