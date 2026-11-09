"""Milestone 1/3: the lexical seam — providers, factory, retrieval mode.

The factory resolves the SQL-backed index when a request session is
provided (milestone 3 Option A) and the explicit ``NullLexicalIndex``
otherwise; null operations are safe no-ops, and the default
``RETRIEVAL_MODE=vector`` must keep the vector-only retrieval behavior
exactly as before.
"""

from __future__ import annotations

import pytest_asyncio

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from app.services.rag import get_lexical_index, get_retriever
from app.services.rag.base import LexicalIndex
from app.services.rag.lexical import NullLexicalIndex, SqlLexicalIndex
from tests.conftest import auth, create_collection

TEST_JWT = "test-secret-key-not-for-production"


@pytest_asyncio.fixture
async def app(tmp_path):
    application = create_app(
        Settings(
            app_env="test",
            jwt_secret_key=TEST_JWT,
            database_url="sqlite+aiosqlite:///:memory:",
            qdrant_url=":memory:",
            storage_dir=str(tmp_path / "uploads"),
            retrieval_mode="vector",
        )
    )
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


# ----------------------------------------------------------------- factory (E)
def test_factory_resolves_null_lexical_index():
    settings = Settings(_env_file=None)
    index = get_lexical_index(settings)
    assert isinstance(index, NullLexicalIndex)
    assert isinstance(index, LexicalIndex)


def test_retriever_receives_lexical_dependency():
    # milestone 3 Option A: the factory forwards the request session, so the
    # retriever gets the real SQL-backed index (search runs on it)
    settings = Settings(_env_file=None)
    retriever = get_retriever(settings, db=object(), vector_store=object())
    assert isinstance(retriever.lexical_index, SqlLexicalIndex)


def test_retriever_without_session_keeps_null_index():
    settings = Settings(_env_file=None)
    retriever = get_retriever(settings, db=None, vector_store=object())
    assert isinstance(retriever.lexical_index, NullLexicalIndex)


# ------------------------------------------------------------ null behaviors (F, G)
async def test_null_search_returns_no_candidates():
    index = NullLexicalIndex()
    results = await index.search(
        query="anything at all",
        tenant_id="00000000-0000-0000-0000-000000000000",
        top_k=10,
    )
    assert results == []


async def test_null_replace_and_delete_are_safe_no_ops():
    index = NullLexicalIndex()
    await index.replace_document(
        tenant_id="00000000-0000-0000-0000-000000000000",
        document_id="00000000-0000-0000-0000-000000000001",
        payloads=[{"chunk_id": "c1", "text": "hello world", "page": 1}],
    )
    await index.delete_document(
        tenant_id="00000000-0000-0000-0000-000000000000",
        document_id="00000000-0000-0000-0000-000000000001",
    )
    assert await index.search(query="hello", tenant_id="t") == []


# ------------------------------------------------- vector mode unchanged (H)
async def test_vector_mode_keeps_vector_only_retrieval(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Policies")
    content = b"Remote work policy allows flextime on Fridays."
    upload = await client.post(
        "/documents/upload",
        files={"file": ("remote.txt", content, "text/plain")},
        data={"collection_id": collection["id"], "classification": "internal"},
        headers=auth(session),
    )
    assert upload.status_code == 201, upload.text
    document = upload.json()
    assert document["status"] == "ready", upload.text

    response = await client.post(
        "/search/retrieve",
        json={"query": "remote work policy flextime", "top_k": 5},
        headers=auth(session),
    )
    assert response.status_code == 200, response.text
    hits = response.json()
    assert hits, "vector retrieval must still return the indexed document"
    assert {hit["documentId"] for hit in hits} == {document["id"]}
    assert isinstance(hits[0]["score"], float)
    assert hits[0]["chunkId"]
    assert "rerankScore" in hits[0]
