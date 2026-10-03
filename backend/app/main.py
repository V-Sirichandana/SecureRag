"""FastAPI application factory.

Routes are mounted twice:

* ``/api/v1/...`` — the canonical, documented prefix (spec)
* ``/...``        — compatibility alias so the existing Next.js frontend
                    (which calls root-relative paths) works unchanged

The alias is hidden from the OpenAPI schema to keep /docs clean.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import install_exception_handlers
from app.core.logging import configure_logging
from app.db.database import create_engine_and_factory
from app.middleware.request_context import RequestContextMiddleware
from app.services.rag import build_vector_store
from app.services.rate_limit import LoginRateLimiter

logger = logging.getLogger("securerag.app")

OPENAPI_TAGS = [
    {"name": "Authentication", "description": "Register, login, refresh and session endpoints."},
    {"name": "Tenants", "description": "Organizations (tenants) and switching between them."},
    {"name": "Users", "description": "Member directory, invitations, roles and status."},
    {
        "name": "Documents",
        "description": "Tenant-scoped document metadata, filters and permissions.",
    },
    {"name": "Collections", "description": "Tenant-scoped knowledge collections."},
    {"name": "Chat", "description": "Conversations and messages."},
    {"name": "Audit", "description": "Audit trail (ADMIN+)."},
    {"name": "API Keys", "description": "Programmatic credentials (hashes only)."},
    {"name": "Usage", "description": "Dashboard, usage and activity analytics."},
    {"name": "Settings", "description": "Per-tenant settings screens (frontend contract)."},
    {"name": "Search", "description": "Global search across the organization."},
    {"name": "Health", "description": "Liveness and readiness probes."},
]

DESCRIPTION = """
SecureRAG backend API.

**Multi-tenancy invariant:** a user belonging to Tenant A must never be able to
access Tenant B's resources. Tenant context is derived server-side from the
authenticated principal's memberships — never from client-supplied ids.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    if not settings.jwt_secret_key:
        if settings.is_production:
            raise RuntimeError(
                "JWT_SECRET_KEY must be set when APP_ENV=production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        settings.jwt_secret_key = secrets.token_urlsafe(48)
        logger.warning(
            "JWT_SECRET_KEY is not set — using an ephemeral development secret. "
            "Tokens will not survive a restart."
        )

    configure_logging(settings)

    engine, session_factory = create_engine_and_factory(
        settings.database_url, echo=settings.debug
    )

    app = FastAPI(
        title=settings.project_name,
        version="1.0.0",
        description=DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.rate_limiter = LoginRateLimiter(settings)
    # one vector store per app instance (per-tenant isolation is enforced in
    # the store itself, never by client input) — never raises at startup
    app.state.vector_store = build_vector_store(settings)

    install_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,  # cookies; never allow "*" with credentials
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count", "X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    # ------------------------------------------------------------------ health
    @app.get("/health", tags=["Health"], summary="Liveness probe")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["Health"], summary="Readiness probe")
    async def ready() -> JSONResponse:
        checks: dict[str, str] = {"database": "ok", "redis": "disabled"}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - readiness must never crash
            logger.exception("Database readiness check failed")
            checks["database"] = "error"

        if settings.redis_url:
            checks["redis"] = "ok"
            try:
                import redis.asyncio as aioredis

                client = aioredis.from_url(settings.redis_url, decode_responses=True)
                try:
                    await client.ping()
                finally:
                    await client.aclose()
            except Exception:  # noqa: BLE001
                logger.warning("Redis readiness check failed")
                checks["redis"] = "error"

        healthy = checks["database"] == "ok"
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={"status": "ready" if healthy else "degraded", "checks": checks},
        )

    # ------------------------------------------------------------------- routes
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(api_router, prefix="", include_in_schema=False)  # frontend alias

    return app


app = create_app()
