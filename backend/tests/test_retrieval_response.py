"""Retrieval response contract: optional rerank_score exposure only."""

from __future__ import annotations

import json

import pytest_asyncio

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from app.schemas.retrieval import RetrievedChunkOut
from tests.conftest import create_collection, make_client
from tests.test_retrieval import retrieve, upload
from tests.test_retrieval_rerank import RecordingReranker

TEST_JWT = "test-secret-key-not-for-production"

EXPECTED_FIELDS = {
    "chunkId",
    "documentId",
    "collectionId",
    "content",
    "score",
    "page",
    "filename",
    "metadata",
    "rerankScore",
}


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


async def upload_note(client, session, collection_id: str) -> dict:
    return await upload(
        client,
        session,
        collection_id=collection_id,
        filename="plan.txt",
        content=b"Quarterly planning note for the engineering org.",
    )


# ------------------------------------------------------------ A: rerank_score
async def test_reranked_response_includes_rerank_score(app, actor_factory):
    client, session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(client, session, name="Docs")
    await upload_note(client, session, collection["id"])

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    hits = response.json()
    assert hits
    assert isinstance(hits[0]["rerankScore"], float)


# -------------------------------------------------- B: vector score preserved
async def test_vector_score_preserved_independently(app, actor_factory):
    client, session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(client, session, name="Docs")
    await upload_note(client, session, collection["id"])

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    hit = response.json()[0]
    assert isinstance(hit["score"], float)
    assert isinstance(hit["rerankScore"], float)

    dumped = RetrievedChunkOut(
        chunk_id="c1", document_id="d1", content="text", score=0.42, rerank_score=1.5
    ).model_dump(by_alias=True)
    assert dumped["score"] == 0.42
    assert dumped["rerankScore"] == 1.5


# --------------------------------------------- C: no reranking -> null score
async def test_response_without_reranking_serializes_null(app, actor_factory, monkeypatch):
    passthrough = RecordingReranker()  # returns chunks untouched: rerank_score None
    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: passthrough)

    client, session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(client, session, name="Docs")
    await upload_note(client, session, collection["id"])

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    hit = response.json()[0]
    assert hit["rerankScore"] is None
    assert isinstance(hit["score"], float)

    schema_dump = RetrievedChunkOut(
        chunk_id="c1", document_id="d1", content="text", score=0.9
    ).model_dump(by_alias=True)
    assert schema_dump["rerankScore"] is None


# --------------------------------------------------- D: response shape stable
async def test_response_fields_remain_unchanged(app, actor_factory):
    client, session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(client, session, name="Docs")
    await upload_note(client, session, collection["id"])

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    hit = response.json()[0]
    assert set(hit) == EXPECTED_FIELDS


# ----------------------------------------------------- E: OpenAPI marks option
async def test_openapi_exposes_rerank_score_as_optional(app):
    async with make_client(app) as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["RetrievedChunkOut"]
    prop = schema["properties"]["rerankScore"]
    assert "rerankScore" not in schema.get("required", [])
    assert "null" in json.dumps(prop)
