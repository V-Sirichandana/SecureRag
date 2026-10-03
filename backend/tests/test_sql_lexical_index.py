"""Milestone 2: SqlLexicalIndex storage semantics.

The index writes through the caller's session with ``flush()`` only — it
never commits. Durability belongs to the caller's commit; a rollback must
discard every staged row. Tenant/document identity comes exclusively from
the method arguments, never from payload fields, and authorization hints
(``created_by`` / ``access`` / ``classification``) are never persisted.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import func, select, text

from app.db.database import create_all, create_engine_and_factory, drop_all
from app.models import Collection, Document, DocumentChunk, Tenant
from app.services.rag.base import LexicalIndex
from app.services.rag.lexical import SqlLexicalIndex

FTS_COUNT = "SELECT count(*) FROM document_chunks_fts"


@pytest_asyncio.fixture
async def session_factory():
    engine, factory = create_engine_and_factory("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    yield factory
    await drop_all(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session


async def seed(db) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A committed tenant + collection + document to satisfy the FKs."""
    tenant = Tenant(name="Acme", slug="acme")
    db.add(tenant)
    await db.flush()
    collection = Collection(tenant_id=tenant.id, name="Docs")
    db.add(collection)
    await db.flush()
    document = Document(
        tenant_id=tenant.id,
        collection_id=collection.id,
        name="guide.txt",
        file_name="guide.txt",
    )
    db.add(document)
    await db.flush()
    await db.commit()
    return tenant.id, collection.id, document.id


def payload(
    chunk_id: str,
    text: str,
    *,
    chunk_index: int = 0,
    page: int = 1,
    collection_id: uuid.UUID | None = None,
) -> dict:
    """A pipeline-shaped payload, plus deliberately WRONG identity values and
    authorization hints that the index must ignore."""
    return {
        "chunk_id": chunk_id,
        "text": text,
        "chunk_index": chunk_index,
        "page": page,
        "filename": "guide.txt",
        "collection_id": str(collection_id) if collection_id else None,
        # hostile/incorrect identity — the method arguments must win
        "tenant_id": "00000000-0000-0000-0000-0000000000fe",
        "document_id": "00000000-0000-0000-0000-0000000000fd",
        # ingest-time hints that must never be persisted or used for authz
        "name": "guide.txt",
        "classification": "confidential",
        "created_by": "00000000-0000-0000-0000-0000000000fc",
        "access": "everyone",
    }


async def count_chunks(db, *, tenant_id: uuid.UUID | None = None) -> int:
    stmt = select(func.count()).select_from(DocumentChunk)
    if tenant_id is not None:
        stmt = stmt.where(DocumentChunk.tenant_id == tenant_id)
    return (await db.execute(stmt)).scalar_one()


async def fts_count(db) -> int:
    return (await db.execute(text(FTS_COUNT))).scalar_one()


# --------------------------------------------------------------- persistence
async def test_replace_persists_required_fields(db):
    tenant_id, collection_id, document_id = await seed(db)
    index = SqlLexicalIndex(db)
    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("chunk-1", "first chunk", chunk_index=0, page=3,
                          collection_id=collection_id)],
    )
    await db.commit()

    row = (await db.execute(select(DocumentChunk))).scalar_one()
    assert row.tenant_id == tenant_id
    assert row.document_id == document_id
    assert row.collection_id == collection_id
    assert row.chunk_id == "chunk-1"
    assert row.chunk_index == 0
    assert row.page == 3
    assert row.filename == "guide.txt"
    assert row.text == "first chunk"
    assert row.created_at is not None
    assert row.updated_at is not None


async def test_payload_identity_cannot_override_arguments(db):
    tenant_id, collection_id, document_id = await seed(db)
    index = SqlLexicalIndex(db)
    # payload carries a foreign tenant_id/document_id — both must be ignored
    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("chunk-1", "text", collection_id=collection_id)],
    )
    await db.commit()

    row = (await db.execute(select(DocumentChunk))).scalar_one()
    assert row.tenant_id == tenant_id
    assert row.document_id == document_id


def test_schema_has_no_authorization_hint_columns():
    columns = set(DocumentChunk.__table__.columns.keys())
    assert columns == {
        "id",
        "tenant_id",
        "document_id",
        "collection_id",
        "chunk_id",
        "chunk_index",
        "page",
        "filename",
        "text",
        "created_at",
        "updated_at",
    }


async def test_authorization_hints_in_payload_are_not_stored(db):
    tenant_id, collection_id, document_id = await seed(db)
    index = SqlLexicalIndex(db)
    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("chunk-1", "text", collection_id=collection_id)],
    )
    await db.commit()

    row = (await db.execute(select(DocumentChunk))).scalar_one()
    for hint in ("created_by", "access", "classification"):
        assert not hasattr(row, hint)


# ----------------------------------------------------- replace / idempotency
async def test_replace_removes_previous_chunks(db):
    tenant_id, collection_id, document_id = await seed(db)
    index = SqlLexicalIndex(db)

    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("old-1", "old alpha text", collection_id=collection_id)],
    )
    await db.commit()
    assert await count_chunks(db) == 1

    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("new-1", "new beta text", collection_id=collection_id)],
    )
    await db.commit()

    rows = (await db.execute(select(DocumentChunk))).scalars().all()
    assert [r.text for r in rows] == ["new beta text"]
    assert [r.chunk_id for r in rows] == ["new-1"]


async def test_repeated_identical_replace_does_not_duplicate(db):
    tenant_id, collection_id, document_id = await seed(db)
    index = SqlLexicalIndex(db)
    payloads = [
        payload("same-1", "identical text one", chunk_index=0, collection_id=collection_id),
        payload("same-2", "identical text two", chunk_index=1, collection_id=collection_id),
    ]

    await index.replace_document(
        tenant_id=str(tenant_id), document_id=str(document_id), payloads=payloads
    )
    await db.commit()
    await index.replace_document(
        tenant_id=str(tenant_id), document_id=str(document_id), payloads=payloads
    )
    await db.commit()

    assert await count_chunks(db) == 2
    chunk_ids = (await db.execute(select(DocumentChunk.chunk_id))).scalars().all()
    assert sorted(chunk_ids) == ["same-1", "same-2"]


# ------------------------------------------------------------------ deletion
async def test_delete_is_scoped_to_tenant_and_document(db):
    tenant_a, collection_id, document_a = await seed(db)
    tenant_b = Tenant(name="Other", slug="other")
    db.add(tenant_b)
    await db.flush()
    document_b = Document(
        tenant_id=tenant_b.id, collection_id=None, name="b.txt", file_name="b.txt"
    )
    db.add(document_b)
    await db.flush()
    # hostile row: tenant B identity pointing at tenant A's document id
    db.add(
        DocumentChunk(
            tenant_id=tenant_b.id,
            document_id=document_a,
            collection_id=None,
            chunk_id="hostile-1",
            chunk_index=0,
            page=1,
            filename="x.txt",
            text="cross tenant row",
        )
    )
    await db.commit()

    index = SqlLexicalIndex(db)
    await index.replace_document(
        tenant_id=str(tenant_a),
        document_id=str(document_a),
        payloads=[payload("a-1", "tenant a chunk", collection_id=collection_id)],
    )
    await index.replace_document(
        tenant_id=str(tenant_b.id),
        document_id=str(document_b.id),
        payloads=[payload("b-1", "tenant b chunk")],
    )
    await db.commit()
    assert await count_chunks(db) == 3

    # tenant A deletes ITS document: A's row goes, everything else stays
    await index.delete_document(tenant_id=str(tenant_a), document_id=str(document_a))
    await db.commit()

    remaining = {
        (str(r.tenant_id), str(r.document_id), r.chunk_id)
        for r in (await db.execute(select(DocumentChunk))).scalars()
    }
    assert (str(tenant_a), str(document_a), "a-1") not in remaining
    assert (str(tenant_b.id), str(document_b.id), "b-1") in remaining
    assert (str(tenant_b.id), str(document_a), "hostile-1") in remaining


async def test_delete_unknown_document_is_safe_noop(db):
    await seed(db)
    index = SqlLexicalIndex(db)
    await index.delete_document(
        tenant_id=str(uuid.uuid4()), document_id=str(uuid.uuid4())
    )
    await db.commit()
    assert await count_chunks(db) == 0


# -------------------------------------------------------- transaction seam
async def test_writes_are_flush_only_never_commit(db, monkeypatch):
    tenant_id, collection_id, document_id = await seed(db)
    index = SqlLexicalIndex(db)

    committed = False

    async def spy_commit():
        nonlocal committed
        committed = True

    monkeypatch.setattr(db, "commit", spy_commit)

    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("chunk-1", "staged", collection_id=collection_id)],
    )
    assert not list(db.new), "rows must be flushed out of the pending state"
    assert await count_chunks(db) == 1, "flushed rows are visible in-session"

    await index.delete_document(tenant_id=str(tenant_id), document_id=str(document_id))
    assert await count_chunks(db) == 0

    assert committed is False, "SqlLexicalIndex must never commit"


async def test_commit_makes_rows_persistent(db, session_factory):
    tenant_id, collection_id, document_id = await seed(db)
    index = SqlLexicalIndex(db)
    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("chunk-1", "durable", collection_id=collection_id)],
    )
    await db.commit()

    # a separate session on the same engine observes the committed row
    async with session_factory() as other:
        assert await count_chunks(other) == 1


async def test_rollback_discards_staged_rows(db, session_factory):
    tenant_id, collection_id, document_id = await seed(db)
    index = SqlLexicalIndex(db)
    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("chunk-1", "doomed", collection_id=collection_id)],
    )
    await db.flush()
    assert await count_chunks(db) == 1

    await db.rollback()
    assert await count_chunks(db) == 0
    async with session_factory() as other:
        assert await count_chunks(other) == 0


# ------------------------------------------------------------ SQLite FTS5
async def test_fts5_mirror_tracks_replace_and_delete(db):
    tenant_id, collection_id, document_id = await seed(db)
    index = SqlLexicalIndex(db)

    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("chunk-1", "alpha keyword", collection_id=collection_id)],
    )
    await db.commit()
    assert await fts_count(db) == 1
    hits = (
        await db.execute(
            text(
                "SELECT chunk_id FROM document_chunks_fts WHERE tenant_id = :t "
                "AND document_id = :d AND document_chunks_fts MATCH :q"
            ),
            {"t": str(tenant_id), "d": str(document_id), "q": "alpha"},
        )
    ).fetchall()
    assert [h[0] for h in hits] == ["chunk-1"]

    # re-ingest replaces the mirror content too
    await index.replace_document(
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        payloads=[payload("chunk-2", "beta keyword", collection_id=collection_id)],
    )
    await db.commit()
    mirror = (
        await db.execute(text("SELECT chunk_id, text FROM document_chunks_fts"))
    ).fetchall()
    assert [(m[0], m[1]) for m in mirror] == [("chunk-2", "beta keyword")]

    await index.delete_document(tenant_id=str(tenant_id), document_id=str(document_id))
    await db.commit()
    assert await fts_count(db) == 0
    assert await count_chunks(db) == 0


# ------------------------------------------------- interface / M2 boundary
def test_sql_index_satisfies_protocol():
    assert isinstance(SqlLexicalIndex(db=None), LexicalIndex)


async def test_search_returns_no_candidates(db):
    """M2 is storage-only: the lexical search seam stays inactive."""
    index = SqlLexicalIndex(db)
    results = await index.search(query="anything", tenant_id=str(uuid.uuid4()))
    assert results == []
