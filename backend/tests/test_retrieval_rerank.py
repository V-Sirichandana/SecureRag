"""Reranker integration: authorization-first pipeline, ordering, limits, safety.

The invariant under test: the reranker only ever receives chunks that already
passed the tenant filter AND the CURRENT database permission check.
"""

from __future__ import annotations

import pytest_asyncio

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from app.services.ingestion.embeddings import HashingEmbeddingProvider
from app.services.rag.base import RetrievedChunk
from app.services.rag.retriever import TenantScopedRetriever
from tests.conftest import create_collection
from tests.test_retrieval import document_ids, retrieve, tenant_of, upload

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
        )
    )
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


class RecordingReranker:
    """Captures exactly what the pipeline allows the reranker to see."""

    def __init__(self, transform=None) -> None:
        self.calls: list[list[RetrievedChunk]] = []
        self._transform = transform

    async def rerank(self, *, query: str, chunks, top_k: int = 5):
        self.calls.append(list(chunks))
        ordered = self._transform(list(chunks)) if self._transform else list(chunks)
        return ordered[:top_k]


class ExplodingReranker:
    async def rerank(self, *, query: str, chunks, top_k: int = 5):
        raise RuntimeError("reranker exploded with api_key=sk-RERANK-LEAK")


class RecordingStore:
    """Scripted rounds; records the requested fetch size of every round."""

    def __init__(self, rounds) -> None:
        self.rounds = rounds
        self.fetches: list[int] = []

    async def search(
        self,
        *,
        vector,
        tenant_id,
        collection_id=None,
        document_ids=None,
        top_k=8,
        extra_filter=None,
    ):
        self.fetches.append(top_k)
        round_index = min(len(self.fetches) - 1, len(self.rounds) - 1)
        return self.rounds[round_index][:top_k]


def chunks_for(document_id: str, count: int, *, prefix: str) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            text=f"{prefix} payload {index}",
            score=0.95 - index * 0.01,
            document_id=document_id,
            chunk_id=f"{document_id}-{index}",
        )
        for index in range(count)
    ]


# ---------------------------------------------- A: authorization BEFORE rerank
async def test_only_authorized_chunks_reach_the_reranker(app, actor_factory, monkeypatch):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    member_client, member_session = await actor_factory(
        name="Mia Member",
        email="mia@acme.com",
        invited_by=(owner_client, owner_session),
        role="member",
    )
    outsider_client, outsider_session = await actor_factory(
        name="Otto Outsider", email="otto@globex.com", org="Globex Inc"
    )

    collection = await create_collection(owner_client, owner_session, name="HR")
    outsider_collection = await create_collection(outsider_client, outsider_session, name="Files")

    # the confidential chunk matches the query EXACTLY — under the reranker it
    # would rank first, so it is the most dangerous candidate to leak
    query = "salary band revision"
    secret = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="secret.txt",
        content=b"salary band revision confidential engineering 2026",
        classification="confidential",
    )
    shared = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="shared.txt",
        content=b"salary review guidelines for the engineering org",
    )
    foreign = await upload(
        outsider_client,
        outsider_session,
        collection_id=outsider_collection["id"],
        filename="foreign.txt",
        content=b"salary band revision confidential engineering 2026",
    )

    recorder = RecordingReranker()
    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: recorder)

    response = await retrieve(member_client, member_session, query=query, top_k=10)
    assert response.status_code == 200, response.text

    assert recorder.calls, "the reranker must have been invoked"
    seen = {chunk.document_id for chunk in recorder.calls[0]}
    assert secret["id"] not in seen, "unauthorized chunk reached the reranker"
    assert foreign["id"] not in seen, "cross-tenant chunk reached the reranker"
    assert shared["id"] in seen, "the authorized chunk must reach the reranker"

    ids = document_ids(response)
    assert ids == {shared["id"]}
    assert secret["id"] not in ids
    assert foreign["id"] not in ids


# ------------------------------------------------- B: reranker changes ordering
async def test_reranker_controls_final_ordering(app, actor_factory, monkeypatch):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(owner_client, owner_session, name="Docs")
    alpha = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="alpha.txt",
        content=b"Alpha note about quarterly planning.",
    )
    beta = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="beta.txt",
        content=b"Beta note about quarterly planning.",
    )

    recorder = RecordingReranker(transform=lambda chunks: list(reversed(chunks)))
    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: recorder)

    response = await retrieve(owner_client, owner_session, query="quarterly planning", top_k=2)
    assert response.status_code == 200, response.text
    hits = response.json()

    pool_ids = [chunk.document_id for chunk in recorder.calls[0]]
    assert set(pool_ids) == {alpha["id"], beta["id"]}
    expected = list(reversed(pool_ids))
    assert expected != pool_ids, "the fake must actually reorder the vector ranking"
    assert [hit["documentId"] for hit in hits] == expected
    assert len(hits) == 2


# ------------------------------------------------------- C: requested top_k
async def test_api_never_returns_more_than_requested_top_k(app, actor_factory):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(owner_client, owner_session, name="Docs")
    for index in range(3):
        await upload(
            owner_client,
            owner_session,
            collection_id=collection["id"],
            filename=f"doc{index}.txt",
            content=f"Quarterly planning note number {index}.".encode(),
        )

    response = await retrieve(owner_client, owner_session, query="quarterly planning", top_k=2)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 2


# ------------------------------------- D: RERANKER_TOP_K as configured limit
async def test_reranker_top_k_caps_results_below_requested(app, actor_factory):
    app.state.settings.reranker_top_k = 3

    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(owner_client, owner_session, name="Docs")
    for index in range(4):
        await upload(
            owner_client,
            owner_session,
            collection_id=collection["id"],
            filename=f"doc{index}.txt",
            content=f"Quarterly planning note number {index}.".encode(),
        )

    response = await retrieve(owner_client, owner_session, query="quarterly planning", top_k=10)
    assert response.status_code == 200, response.text
    hits = response.json()
    assert len(hits) == 3  # RERANKER_TOP_K, and never more than requested


# ------------------------------------------- E: min(top_k * 3, MAX_CANDIDATES)
async def test_candidate_fetch_respects_reranker_limits(app, actor_factory):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(owner_client, owner_session, name="Docs")
    document = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="shared.txt",
        content=b"Shared quarterly planning content.",
    )

    store = RecordingStore([chunks_for(document["id"], 20, prefix="cand")])
    recorder = RecordingReranker()
    async with app.state.session_factory() as db:
        retriever = TenantScopedRetriever(
            db=db,
            embedder=HashingEmbeddingProvider(dimension=384),
            vector_store=store,
            reranker=recorder,
            rerank_top_k=10,
            rerank_max_candidates=20,
        )
        results = await retriever.retrieve(
            query="planning content",
            tenant_id=tenant_of(owner_session),
            user_id=owner_session["user"]["id"],
            top_k=10,
        )

    assert store.fetches[0] == 20  # min(top_k * 3 = 30, RERANKER_MAX_CANDIDATES = 20)
    assert store.fetches == [20]  # enough authorized results in round 1
    assert len(results) == 10


# ------------------------------------------------------- F: small result sets
async def test_small_result_sets_do_not_expand_unnecessarily(app, actor_factory):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(owner_client, owner_session, name="Docs")
    document = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="shared.txt",
        content=b"Shared quarterly planning content.",
    )

    store = RecordingStore([chunks_for(document["id"], 6, prefix="cand")])
    recorder = RecordingReranker()
    async with app.state.session_factory() as db:
        retriever = TenantScopedRetriever(
            db=db,
            embedder=HashingEmbeddingProvider(dimension=384),
            vector_store=store,
            reranker=recorder,
            rerank_top_k=5,
            rerank_max_candidates=40,
        )
        results = await retriever.retrieve(
            query="planning content",
            tenant_id=tenant_of(owner_session),
            user_id=owner_session["user"]["id"],
            top_k=2,
        )

    assert store.fetches == [6]  # min(2 * 3, 40) = 6: one round, no expansion
    assert len(results) == 2


# ------------------------------------------------- I: safe reranker failures
async def test_reranker_failure_returns_safe_error(app, actor_factory, monkeypatch):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    collection = await create_collection(owner_client, owner_session, name="Docs")
    await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="doc.txt",
        content=b"Quarterly planning note.",
    )

    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: ExplodingReranker())

    response = await retrieve(owner_client, owner_session, query="quarterly planning")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    body = response.text.lower()
    assert "sk-rerank-leak" not in body
    assert "traceback" not in body


# ------------------------------------------ J: unconfigured provider stays 501
async def test_unknown_reranker_provider_fails_safe(app, actor_factory):
    app.state.settings.reranker_provider = "does-not-exist"

    client, session = await actor_factory(
        name="Cfg Checker", email="cfg@example.com", org="Config Co"
    )
    response = await retrieve(client, session, query="anything at all")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "SERVICE_NOT_CONFIGURED"
    body = response.text.lower()
    assert "does-not-exist" in body  # controlled message names the provider
    assert "traceback" not in body
