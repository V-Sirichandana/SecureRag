"""Milestone 2: lexical rows follow the ingestion lifecycle over the API.

``document_chunks`` is written through the SAME session/transaction as the
document status, so:

* ``ready``  → exactly ``chunkCount`` rows, fully tenant-scoped;
* ``failed`` → zero rows (rollback + compensation, never stale content);
* delete/re-ingest keep canonical rows and the SQLite FTS5 mirror in sync;
* one tenant's ingestion can never touch another tenant's rows.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from app.models import DocumentChunk
from app.services.rag.lexical import SqlLexicalIndex
from tests.conftest import (
    auth,
    create_collection,
    make_client,
    register,
)

TEST_JWT = "test-secret-key-not-for-production"

ALPHA = b"Alpha policy describes vacation rules for all engineers."
ZETA = b"Zeta protocol describes failover rules for all clusters."


def build_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        jwt_secret_key=TEST_JWT,
        database_url="sqlite+aiosqlite:///:memory:",
        qdrant_url=":memory:",
        max_upload_bytes=65536,
    )
    base.update(overrides)
    return Settings(**base)


@pytest_asyncio.fixture
async def app(tmp_path):
    application = create_app(build_settings(storage_dir=str(tmp_path / "uploads")))
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


@pytest_asyncio.fixture
async def app_no_vector_store(tmp_path):
    application = create_app(build_settings(qdrant_url="", storage_dir=str(tmp_path / "nvs")))
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


async def upload(
    client,
    session: dict,
    *,
    collection_id: str,
    filename: str,
    content: bytes,
    content_type: str = "text/plain",
    classification: str = "internal",
):
    return await client.post(
        "/documents/upload",
        files={"file": (filename, content, content_type)},
        data={"collection_id": collection_id, "classification": classification},
        headers=auth(session),
    )


async def lexical_rows(
    app,
    *,
    tenant_id: str,
    document_id: str | None = None,
) -> list[dict]:
    """Committed canonical rows, detached as plain dicts (fresh session)."""
    async with app.state.session_factory() as db:
        stmt = select(DocumentChunk).where(
            DocumentChunk.tenant_id == uuid.UUID(str(tenant_id))
        )
        if document_id is not None:
            stmt = stmt.where(DocumentChunk.document_id == uuid.UUID(str(document_id)))
        rows = (await db.execute(stmt.order_by(DocumentChunk.chunk_index))).scalars().all()
        return [
            {
                "tenant_id": str(r.tenant_id),
                "document_id": str(r.document_id),
                "collection_id": str(r.collection_id) if r.collection_id else None,
                "chunk_id": r.chunk_id,
                "chunk_index": r.chunk_index,
                "page": r.page,
                "filename": r.filename,
                "text": r.text,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]


async def fts_texts(app) -> list[str]:
    """Committed SQLite FTS5 mirror texts (empty on non-SQLite dialects is N/A
    here — the test suite always runs on SQLite)."""
    async with app.state.session_factory() as db:
        result = await db.execute(text("SELECT text FROM document_chunks_fts"))
        return [row[0] for row in result.fetchall()]


# ------------------------------------------------------------- ready document
async def test_successful_ingestion_persists_lexical_rows(app, actor_factory):
    client, session = await actor_factory(
        name="Ada", email="ada@example.com", org="Acme Corp"
    )
    collection = await create_collection(client, session, name="Handbook")
    created = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="policy.txt",
        content=ALPHA,
    )
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["status"] == "ready"
    chunk_count = document["chunkCount"]
    assert chunk_count >= 1

    tenant_id = session["user"]["organizationId"]
    rows = await lexical_rows(app, tenant_id=tenant_id, document_id=document["id"])
    assert len(rows) == chunk_count
    for row in rows:
        assert row["tenant_id"] == tenant_id
        assert row["document_id"] == document["id"]
        assert row["collection_id"] == collection["id"]
        assert row["filename"] == "policy.txt"
        assert row["page"] >= 1
        assert row["text"]
        assert row["created_at"] is not None
        assert row["updated_at"] is not None
    assert [r["chunk_index"] for r in rows] == list(range(chunk_count))
    assert len({r["chunk_id"] for r in rows}) == chunk_count

    # the SQLite mirror tracks exactly the canonical texts
    assert sorted(await fts_texts(app)) == sorted(r["text"] for r in rows)


# ------------------------------------------------------------ failed document
async def test_failed_ingestion_leaves_zero_lexical_rows(app, actor_factory):
    client, session = await actor_factory(
        name="Fail", email="fail@example.com", org="Broken Inc"
    )
    collection = await create_collection(client, session, name="Ingestion")
    created = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="corrupt.pdf",
        content=b"%PDF-1.4 truncated garbage without an xref table",
        content_type="application/pdf",
    )
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["status"] == "failed"

    tenant_id = session["user"]["organizationId"]
    assert await lexical_rows(app, tenant_id=tenant_id, document_id=document["id"]) == []
    assert await fts_texts(app) == []


async def test_vector_store_failure_leaves_zero_lexical_rows(app_no_vector_store):
    client = make_client(app_no_vector_store)
    async with client:
        session = await register(client, name="Neo", email="neo@example.com", org="Zion")
        collection = await create_collection(client, session, name="Offline")
        created = await upload(
            client,
            session,
            collection_id=collection["id"],
            filename="offline.txt",
            content=b"no vector backend is configured for this deployment",
        )
        assert created.status_code == 201, created.text
        document = created.json()
        assert document["status"] == "failed"

        tenant_id = session["user"]["organizationId"]
        rows = await lexical_rows(
            app_no_vector_store, tenant_id=tenant_id, document_id=document["id"]
        )
        assert rows == []
        assert await fts_texts(app_no_vector_store) == []


async def test_reingest_failure_leaves_zero_lexical_rows(app, actor_factory, monkeypatch):
    client, session = await actor_factory(
        name="Ren", email="ren@example.com", org="Retry Inc"
    )
    collection = await create_collection(client, session, name="Staged")
    created = await upload(
        client, session, collection_id=collection["id"], filename="guide.txt", content=ALPHA
    )
    assert created.status_code == 201
    document = created.json()
    assert document["status"] == "ready"
    tenant_id = session["user"]["organizationId"]
    before = await lexical_rows(
        app, tenant_id=tenant_id, document_id=document["id"]
    )
    assert len(before) == document["chunkCount"]

    async def _boom(**kwargs):
        raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr(app.state.vector_store, "upsert_chunks", _boom)

    reingest = await client.post(
        f"/documents/{document['id']}/content",
        files={"file": ("guide.txt", ZETA, "text/plain")},
        headers=auth(session),
    )
    assert reingest.status_code == 200, reingest.text
    assert reingest.json()["status"] == "failed"

    # rollback restored the PREVIOUS rows → compensation must delete them too
    assert await lexical_rows(app, tenant_id=tenant_id, document_id=document["id"]) == []
    assert await fts_texts(app) == []


# -------------------------------------------------------------------- delete
async def test_delete_document_removes_lexical_rows(app, actor_factory):
    client, session = await actor_factory(
        name="Dana", email="dana@example.com", org="Cleanup Co"
    )
    collection = await create_collection(client, session, name="Temporary")
    created = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="transient.txt",
        content=b"ephemeral knowledge that must vanish on delete",
    )
    assert created.status_code == 201
    document_id = created.json()["id"]
    tenant_id = session["user"]["organizationId"]
    assert await lexical_rows(app, tenant_id=tenant_id, document_id=document_id)

    deleted = await client.delete(f"/documents/{document_id}", headers=auth(session))
    assert deleted.status_code == 204

    assert await lexical_rows(app, tenant_id=tenant_id, document_id=document_id) == []
    assert await fts_texts(app) == []


# ------------------------------------------------------------------ re-ingest
async def test_reingest_replaces_lexical_rows(app, actor_factory):
    client, session = await actor_factory(
        name="Rea", email="rea@example.com", org="Retry Inc"
    )
    collection = await create_collection(client, session, name="Staged")
    created = await upload(
        client, session, collection_id=collection["id"], filename="guide.txt", content=ALPHA
    )
    assert created.status_code == 201
    document = created.json()
    assert document["status"] == "ready"
    tenant_id = session["user"]["organizationId"]

    reingest = await client.post(
        f"/documents/{document['id']}/content",
        files={"file": ("guide.txt", ZETA, "text/plain")},
        headers=auth(session),
    )
    assert reingest.status_code == 200, reingest.text
    updated = reingest.json()
    assert updated["status"] == "ready"

    rows = await lexical_rows(app, tenant_id=tenant_id, document_id=document["id"])
    assert len(rows) == updated["chunkCount"]  # replaced, never appended
    joined = " ".join(r["text"] for r in rows)
    assert "Zeta" in joined
    assert "Alpha" not in joined
    assert len({r["chunk_id"] for r in rows}) == len(rows)  # no duplicates
    assert sorted(await fts_texts(app)) == sorted(r["text"] for r in rows)


async def test_reingest_identical_content_keeps_chunk_ids_stable(app, actor_factory):
    client, session = await actor_factory(
        name="Stu", email="stu@example.com", org="Stable Inc"
    )
    collection = await create_collection(client, session, name="Stable")
    created = await upload(
        client, session, collection_id=collection["id"], filename="guide.txt", content=ALPHA
    )
    assert created.status_code == 201
    document = created.json()
    tenant_id = session["user"]["organizationId"]
    first_ids = {
        r["chunk_id"]
        for r in await lexical_rows(app, tenant_id=tenant_id, document_id=document["id"])
    }

    reingest = await client.post(
        f"/documents/{document['id']}/content",
        files={"file": ("guide.txt", ALPHA, "text/plain")},
        headers=auth(session),
    )
    assert reingest.status_code == 200
    assert reingest.json()["status"] == "ready"

    second_ids = {
        r["chunk_id"]
        for r in await lexical_rows(app, tenant_id=tenant_id, document_id=document["id"])
    }
    assert second_ids == first_ids


# ----------------------------------------------------------- tenant isolation
async def test_ingestion_does_not_cross_tenant_rows(app, actor_factory):
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    collection_a = await create_collection(client_a, session_a, name="Acme Files")
    collection_b = await create_collection(client_b, session_b, name="Globex Files")

    created_a = await upload(
        client_a,
        session_a,
        collection_id=collection_a["id"],
        filename="acme.txt",
        content=b"Acme secret merger documents are stored safely.",
    )
    created_b = await upload(
        client_b,
        session_b,
        collection_id=collection_b["id"],
        filename="globex.txt",
        content=b"Globex rocket shipping specs are stored safely.",
    )
    assert created_a.status_code == 201 and created_b.status_code == 201
    document_a = created_a.json()["id"]
    document_b = created_b.json()["id"]
    tenant_a = session_a["user"]["organizationId"]
    tenant_b = session_b["user"]["organizationId"]

    rows_a = await lexical_rows(app, tenant_id=tenant_a)
    rows_b = await lexical_rows(app, tenant_id=tenant_b)
    assert {r["document_id"] for r in rows_a} == {document_a}
    assert {r["document_id"] for r in rows_b} == {document_b}
    assert all(r["tenant_id"] == tenant_a for r in rows_a)
    assert all(r["tenant_id"] == tenant_b for r in rows_b)


async def test_tenant_cannot_delete_another_tenants_rows(app, actor_factory):
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    collection_a = await create_collection(client_a, session_a, name="Acme Files")
    created = await upload(
        client_a,
        session_a,
        collection_id=collection_a["id"],
        filename="acme.txt",
        content=b"Acme secret merger documents are stored safely.",
    )
    assert created.status_code == 201
    document_a = created.json()["id"]
    tenant_a = session_a["user"]["organizationId"]
    tenant_b = session_b["user"]["organizationId"]
    rows_a = await lexical_rows(app, tenant_id=tenant_a, document_id=document_a)
    assert rows_a

    # tenant B's session deletes rows addressed by tenant A's document id
    async with app.state.session_factory() as db:
        index = SqlLexicalIndex(db)
        await index.delete_document(tenant_id=tenant_b, document_id=document_a)
        await db.commit()

    after = await lexical_rows(app, tenant_id=tenant_a, document_id=document_a)
    assert after == rows_a  # scoped delete: B's tenant matched nothing
