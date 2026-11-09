"""Health/readiness probes: database and Qdrant failures are reported safely."""

from __future__ import annotations

import pytest_asyncio

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from tests.conftest import make_client

TEST_JWT = "test-secret-key-not-for-production"


def build_settings(tmp_path, **overrides) -> Settings:
    base = dict(
        _env_file=None,
        app_env="test",
        jwt_secret_key=TEST_JWT,
        database_url="sqlite+aiosqlite:///:memory:",
        qdrant_url=":memory:",
        storage_dir=str(tmp_path / "uploads"),
    )
    base.update(overrides)
    return Settings(**base)


@pytest_asyncio.fixture
async def isolated_app(tmp_path):
    application = create_app(build_settings(tmp_path))
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


async def test_liveness_never_checks_dependencies(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_reports_database_and_qdrant(isolated_app):
    async with make_client(isolated_app) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "disabled", "qdrant": "ok"},
    }


async def test_readiness_reports_qdrant_connection_failure(isolated_app, monkeypatch):
    class FailingVectorStore:
        def check_health(self) -> None:
            raise RuntimeError("connection refused")

    monkeypatch.setattr(isolated_app.state, "vector_store", FailingVectorStore())

    async with make_client(isolated_app) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["qdrant"] == "error"
    assert "connection refused" not in response.text


async def test_readiness_reports_qdrant_disabled_without_url(tmp_path):
    application = create_app(build_settings(tmp_path, qdrant_url=""))
    await create_all(application.state.engine)
    try:
        async with make_client(application) as client:
            response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["checks"]["qdrant"] == "disabled"
    finally:
        await drop_all(application.state.engine)
        await application.state.engine.dispose()
