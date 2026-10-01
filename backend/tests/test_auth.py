"""Authentication: registration, login, cookies, refresh, logout, rate limit."""

from __future__ import annotations

from tests.conftest import auth, login, make_client, register


async def test_register_returns_session_and_sets_cookies(client):
    session = await register(
        client, name="Alice", email="alice@example.com", org="Acme"
    )
    assert session["user"]["email"] == "alice@example.com"
    assert session["user"]["role"] == "owner"
    assert session["accessToken"]
    assert "sr_access_token" in client.cookies
    assert "sr_refresh_token" in client.cookies
    assert client.cookies["sr_tenant"] == session["user"]["organizationId"]


async def test_me_works_with_cookies_only(app):
    async with make_client(app) as client:
        await register(client, name="Alice", email="alice@example.com", org="Acme")
        response = await client.get("/auth/me")  # no Authorization header
        assert response.status_code == 200
        assert response.json()["user"]["email"] == "alice@example.com"


async def test_me_works_with_bearer_token(app):
    async with make_client(app) as cookie_client:
        session = await register(
            cookie_client, name="Alice", email="alice@example.com", org="Acme"
        )
    async with make_client(app) as bearer_client:
        response = await bearer_client.get("/auth/me", headers=auth(session))
        assert response.status_code == 200


async def test_login_with_correct_password(app):
    async with make_client(app) as register_client:
        await register(register_client, name="Alice", email="alice@example.com", org="Acme")
    async with make_client(app) as login_client:
        session = await login(login_client, email="alice@example.com")
        assert session["user"]["email"] == "alice@example.com"
        assert "sr_access_token" in login_client.cookies


async def test_login_with_wrong_password_is_401(app):
    async with make_client(app) as register_client:
        await register(register_client, name="Alice", email="alice@example.com", org="Acme")
    async with make_client(app) as login_client:
        response = await login_client.post(
            "/auth/login",
            json={"email": "alice@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["error"]["code"] == "INVALID_CREDENTIALS"
        assert body["detail"]  # the Next.js client reads detail directly


async def test_login_unknown_account_is_401(app):
    async with make_client(app) as client:
        response = await client.post(
            "/auth/login",
            json={"email": "ghost@example.com", "password": "password123"},
        )
        assert response.status_code == 401


async def test_signup_alias_matches_register(app):
    async with make_client(app) as client:
        response = await client.post(
            "/auth/signup",
            json={
                "name": "Bob",
                "email": "bob@example.com",
                "password": "password123",
                "organization_name": "Globex",
            },
        )
        assert response.status_code == 201
        assert response.json()["user"]["role"] == "owner"


async def test_duplicate_email_is_409(app):
    async with make_client(app) as first:
        await register(first, name="Alice", email="alice@example.com", org="Acme")
    async with make_client(app) as second:
        response = await second.post(
            "/auth/register",
            json={
                "name": "Alice Again",
                "email": "alice@example.com",
                "password": "password123",
                "organization_name": "Other Org",
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_EXISTS"


async def test_refresh_rotates_tokens(app):
    async with make_client(app) as client:
        await register(client, name="Alice", email="alice@example.com", org="Acme")
        response = await client.post("/auth/refresh")
        assert response.status_code == 200
        body = response.json()
        assert body["accessToken"]


async def test_logout_clears_session(app):
    async with make_client(app) as client:
        await register(client, name="Alice", email="alice@example.com", org="Acme")
        logout = await client.post("/auth/logout")
        assert logout.status_code == 204
        me = await client.get("/auth/me")
        assert me.status_code == 401


async def test_protected_route_without_token_is_401(client):
    response = await client.get("/documents")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "AUTH_REQUIRED"
    assert body["detail"]


async def test_login_rate_limit(app):
    async with make_client(app) as register_client:
        await register(register_client, name="Alice", email="alice@example.com", org="Acme")

    async with make_client(app) as client:
        statuses = []
        for _ in range(6):
            response = await client.post(
                "/auth/login",
                json={"email": "alice@example.com", "password": "wrong-password"},
            )
            statuses.append(response.status_code)
        # attempts 1-5 are bad credentials, the 6th trips the limiter
        assert statuses[:5] == [401] * 5
        assert statuses[5] == 429
        assert response.json()["error"]["code"] == "TOO_MANY_REQUESTS"
