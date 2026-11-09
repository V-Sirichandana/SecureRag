"""Engine setup: SQLite-only hooks must not run on PostgreSQL connections."""

from __future__ import annotations

from sqlalchemy import event

from app.db.database import _enable_sqlite_foreign_keys, create_engine_and_factory


async def test_foreign_key_pragma_listener_is_sqlite_only():
    sqlite_engine, _ = create_engine_and_factory("sqlite+aiosqlite:///:memory:")
    postgres_engine, _ = create_engine_and_factory(
        "postgresql+asyncpg://user:pass@localhost:5432/test"
    )
    try:
        assert event.contains(
            sqlite_engine.sync_engine, "connect", _enable_sqlite_foreign_keys
        )
        assert not event.contains(
            postgres_engine.sync_engine, "connect", _enable_sqlite_foreign_keys
        )
    finally:
        await sqlite_engine.dispose()
        await postgres_engine.dispose()
