"""M5.1 security regression: search/retrieve rate limiting (scope="search").

GET /search and POST /search/retrieve share ONE fixed-window bucket keyed by
the server-derived authenticated user id, checked BEFORE any query, embed or
vector work. Tenant switching, other users, other scopes (login) and
unauthenticated requests must stay unaffected, and a rejected request never
reaches the vector store.
"""

from __future__ import annotations

import pytest_asyncio

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from tests.conftest import auth, login, make_client

TEST_JWT = "test-secret-key-not-for-production"
LIMIT = 5  # Settings.rate_limit_login_attempts default — shared by every scope


@pytest_asyncio.fixture
async def app(tmp_path):
    application = create_app(
        Settings(
            app_env="test",
            jwt_secret_key=TEST_JWT,
            database_url="sqlite+aiosqlite:///:memory:",
            qdrant_url=":memory:",
            storage_dir=str(tmp_path / "uploads"),
        )
    )
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


async def search(client, session, *, headers: dict | None = None):
    return await client.get(
        "/search", params={"q": "anything"}, headers={**auth(session), **(headers or {})}
    )


async def retrieve_request(client, session):
    return await client.post(
        "/search/retrieve",
        json={"query": "anything", "top_k": 5},
        headers=auth(session),
    )


# ------------------------------------------- A. five allowed, sixth rejected
async def test_search_budget_allows_five_then_429(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")

    allowed = [await search(client, session) for _ in range(LIMIT)]
    assert [response.status_code for response in allowed] == [200] * LIMIT

    blocked = await search(client, session)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "TOO_MANY_REQUESTS"


# ------------------------------------- B. both endpoints share one bucket
async def test_get_search_and_retrieve_share_one_bucket(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")

    for _ in range(2):
        assert (await search(client, session)).status_code == 200
    for _ in range(3):
        assert (await retrieve_request(client, session)).status_code == 200

    # 6th search-scope request — spent half on each endpoint — is rejected
    blocked_get = await search(client, session)
    assert blocked_get.status_code == 429

    # the reverse direction: a retrieve-only bucket blocks GET /search too
    other_client, other_session = await actor_factory(
        name="Bob", email="bob@example.com", org="Globex"
    )
    for _ in range(LIMIT):
        assert (await search(other_client, other_session)).status_code == 200
    blocked_post = await retrieve_request(other_client, other_session)
    assert blocked_post.status_code == 429
    assert blocked_post.json()["error"]["code"] == "TOO_MANY_REQUESTS"


# ------------------------------------------- C. tenant switching is no reset
async def test_tenant_switching_cannot_reset_the_search_bucket(app, actor_factory):
    owner_a, session_a = await actor_factory(
        name="Alice", email="alice@example.com", org="Acme Corp"
    )
    owner_b, session_b = await actor_factory(
        name="Bob", email="bob@example.org", org="Globex Inc"
    )

    # Alice joins Globex as well → she now has two valid tenant contexts
    invite = await owner_b.post(
        "/users/invite",
        json={"email": "alice@example.com", "role": "member", "department": "Engineering"},
        headers=auth(session_b),
    )
    assert invite.status_code == 201, invite.text

    tenant_a = session_a["user"]["organizationId"]
    tenant_b = session_b["user"]["organizationId"]

    statuses = []
    for index in range(LIMIT + 1):
        headers = {**auth(session_a), "X-Tenant-Id": tenant_b if index % 2 else tenant_a}
        response = await owner_a.get("/search", params={"q": "anything"}, headers=headers)
        statuses.append(response.status_code)

    assert statuses[:LIMIT] == [200] * LIMIT, "each tenant context is valid on its own"
    assert statuses[LIMIT] == 429, "the bucket follows the user id, never the tenant"


# ------------------------------------------------ D. buckets are per-user
async def test_search_buckets_are_per_user(app, actor_factory):
    client_a, session_a = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    client_b, session_b = await actor_factory(name="Bob", email="bob@example.com", org="Globex")

    for _ in range(LIMIT):
        assert (await search(client_a, session_a)).status_code == 200
    assert (await search(client_a, session_a)).status_code == 429  # A is exhausted

    assert (await search(client_b, session_b)).status_code == 200  # B is untouched


# ------------------------------- E. unauthenticated requests never count
async def test_unauthenticated_requests_do_not_consume_the_bucket(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")

    async with make_client(app) as anonymous:
        for _ in range(3):
            response = await anonymous.get("/search", params={"q": "anything"})
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "AUTH_REQUIRED"

    allowed = [await search(client, session) for _ in range(LIMIT)]
    assert [response.status_code for response in allowed] == [200] * LIMIT


# -------------------------- F. rejected requests never reach the vector store
async def test_rejected_requests_never_reach_the_vector_store(app, actor_factory, monkeypatch):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")

    calls: list[dict] = []
    original = app.state.vector_store.search

    async def spy(**kwargs):
        calls.append(kwargs)
        return await original(**kwargs)

    monkeypatch.setattr(app.state.vector_store, "search", spy)

    first = await retrieve_request(client, session)
    assert first.status_code == 200, first.text
    assert len(calls) == 1, "the spy must be wired before the limit is hit"

    for _ in range(4):
        assert (await search(client, session)).status_code == 200  # bucket now 5/5

    blocked = await retrieve_request(client, session)
    assert blocked.status_code == 429
    assert len(calls) == 1, "the limit short-circuits BEFORE any vector work"


# ------------------------------------------- G. scopes never collide
async def test_exhausted_search_scope_does_not_block_login(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")

    for _ in range(LIMIT):
        assert (await search(client, session)).status_code == 200
    assert (await search(client, session)).status_code == 429

    relogin = await login(client, email="ada@example.com")
    assert relogin["accessToken"], "the login scope is a separate bucket"


async def test_exhausted_login_scope_does_not_block_search(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")

    for _ in range(LIMIT):
        failed = await client.post(
            "/auth/login",
            json={"email": "ada@example.com", "password": "wrong-password"},
        )
        assert failed.status_code == 401
    blocked_login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "wrong-password"},
    )
    assert blocked_login.status_code == 429

    allowed = [await search(client, session) for _ in range(LIMIT)]
    assert [response.status_code for response in allowed] == [200] * LIMIT
