"""Shared test fixtures: one in-memory SQLite app + an ASGI client per actor."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app

PASSWORD = "password123"


def make_settings() -> Settings:
    return Settings(
        app_env="test",
        jwt_secret_key="test-secret-key-not-for-production",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="",
        cors_origins="http://localhost:3000",
        debug=False,
    )


@pytest_asyncio.fixture
async def app():
    application = create_app(make_settings())
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


def make_client(app) -> AsyncClient:
    """A fresh client with its own cookie jar (one jar per actor)."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest_asyncio.fixture
async def client(app):
    async with make_client(app) as test_client:
        yield test_client


async def register(
    client: AsyncClient,
    *,
    name: str,
    email: str,
    org: str,
    password: str = PASSWORD,
) -> dict:
    response = await client.post(
        "/auth/register",
        json={
            "name": name,
            "email": email,
            "password": password,
            "organization_name": org,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login(client: AsyncClient, *, email: str, password: str = PASSWORD) -> dict:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def auth(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['accessToken']}"}


async def accept_invite(client: AsyncClient, invite: dict) -> None:
    """Invited accounts set their first password through the public endpoint."""
    response = await client.post(
        "/auth/accept-invite",
        json={"token": invite["inviteToken"], "password": PASSWORD},
    )
    assert response.status_code == 200, response.text


@pytest_asyncio.fixture
async def actor_factory(app) -> Callable[..., Awaitable[tuple[AsyncClient, dict]]]:
    """Create isolated actors: ``client, session = await factory(...)``.

    ``invited_by=(owner_client, owner_session)`` invites + activates the actor
    inside the owner's organization instead of creating a new one.
    """
    clients: list[AsyncClient] = []

    async def factory(
        *,
        name: str,
        email: str,
        org: str = "Default Org",
        role: str | None = None,
        invited_by: tuple[AsyncClient, dict] | None = None,
    ) -> tuple[AsyncClient, dict]:
        actor = make_client(app)
        await actor.__aenter__()
        clients.append(actor)
        if invited_by is None:
            session = await register(actor, name=name, email=email, org=org)
        else:
            owner_client, owner_session = invited_by
            invite = await owner_client.post(
                "/users/invite",
                json={"email": email, "role": role or "member", "department": "Engineering"},
                headers=auth(owner_session),
            )
            assert invite.status_code == 201, invite.text
            await accept_invite(actor, invite.json())
            session = await login(actor, email=email)
        return actor, session

    yield factory
    for actor in clients:
        await actor.__aexit__(None, None, None)


async def create_collection(
    client: AsyncClient, session: dict, *, name: str = "Handbook"
) -> dict:
    response = await client.post(
        "/collections", json={"name": name}, headers=auth(session)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_document(
    client: AsyncClient,
    session: dict,
    *,
    collection_id: str,
    name: str = "Q3 Report.pdf",
    classification: str = "internal",
) -> dict:
    response = await client.post(
        "/documents",
        json={
            "name": name,
            "collection_id": collection_id,
            "classification": classification,
            "page_count": 3,
        },
        headers=auth(session),
    )
    assert response.status_code == 201, response.text
    return response.json()
