"""Async SQLAlchemy engine / session factory."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool, StaticPool

from app.models.base import Base

# SQLite (tests / local smoke runs) needs a static pool so every connection
# shares the same in-memory database.
_SQLITE_KWARGS: dict = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
_ASYNC_POOL_KWARGS: dict = {"poolclass": AsyncAdaptedQueuePool, "pool_pre_ping": True}


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite does not enforce foreign keys by default — turn them on."""
    if not hasattr(dbapi_connection, "cursor"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_engine_and_factory(
    database_url: str, *, echo: bool = False
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    kwargs: dict = {"echo": echo, "future": True}
    if database_url.startswith("sqlite"):
        kwargs.update(_SQLITE_KWARGS)
    else:
        kwargs.update(_ASYNC_POOL_KWARGS)

    engine = create_async_engine(database_url, **kwargs)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def create_all(engine: AsyncEngine) -> None:
    """Create tables directly from the models (used by tests / smoke runs)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
