"""Milestone 4: hybrid retrieval — RRF fusion behind a single auth choke point.

What is under test:

* mode wiring: vector mode stays exactly as before (the lexical index is
  never consulted), hybrid activates both sources exactly once each, and
  the mode is server-side only — ``RetrieveIn`` cannot select it;
* fusion: RRF with ``RRF_K = 60`` over 1-based SOURCE RANKS only (raw
  vector/lexical scores never enter the formula), dedup by ``chunk_id``
  with the vector chunk as carrier, deterministic tie-breaking
  (fused DESC → vector rank ASC → lexical rank ASC → chunk_id ASC);
* security: each source keeps its own server-derived tenant fence, ONE
  CURRENT permission check covers the union, unauthorized candidates never
  receive a fused score nor reach the reranker, and grants/revokes/role
  rules take effect with no re-ingestion;
* bounds: fetch ≤ 40 per source, union ≤ 80, reranker pool ≤ 40, final
  result ≤ min(top_k, rerank_top_k);
* failure: any source failure → controlled 503, hybrid without a lexical
  index → 501 (never a silent vector-only fallback), empty source results
  are NOT failures, vector-mode failure semantics untouched;
* score semantics: vector mode ``score`` = vector similarity, hybrid mode
  ``score`` = fused RRF score, ``rerankScore`` unchanged/provider-specific,
  response shape byte-identical in both modes.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.core.config import Settings
from app.core.exceptions import AppError
from app.db.database import create_all, drop_all
from app.main import create_app
from app.services.ingestion.embeddings import HashingEmbeddingProvider
from app.services.rag import get_retriever
from app.services.rag.base import RetrievedChunk
from app.services.rag.lexical import NullLexicalIndex, SqlLexicalIndex
from app.services.rag.retriever import (
    MAX_CANDIDATES,
    RRF_K,
    TenantScopedRetriever,
    _FusedCandidate,
    _recompute_source_ranks,
    _rrf_fuse,
    _union_candidates,
)
from tests.conftest import auth, create_collection, create_document
from tests.test_retrieval import document_ids, retrieve, tenant_of, upload
from tests.test_retrieval_rerank import ExplodingReranker, RecordingReranker
from tests.test_retrieval_response import EXPECTED_FIELDS

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
            retrieval_mode="hybrid",
        )
    )
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


# ------------------------------------------------------------------ helpers
def make_chunk(
    chunk_id: str,
    *,
    score: float = 0.9,
    document_id: str = "00000000-0000-0000-0000-000000000000",
    text: str = "payload text",
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text, score=score, document_id=document_id, chunk_id=chunk_id
    )


def synthetic(
    document_id: str, count: int, *, prefix: str, start: float = 0.95
) -> list[RetrievedChunk]:
    return [
        make_chunk(
            f"{prefix}-{index:03d}",
            score=start - index * 0.01,
            document_id=document_id,
            text=f"{prefix} payload {index}",
        )
        for index in range(count)
    ]


def install_lexical_spy(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    original = SqlLexicalIndex.search

    async def spy(self, **kwargs):
        calls.append(kwargs)
        return await original(self, **kwargs)

    monkeypatch.setattr(SqlLexicalIndex, "search", spy)
    return calls


def install_auth_spy(monkeypatch) -> list[int]:
    """Record the candidate count of every _visible_document_ids call."""
    sizes: list[int] = []
    original = TenantScopedRetriever._visible_document_ids

    async def spy(self, **kwargs):
        sizes.append(len(kwargs["candidates"]))
        return await original(self, **kwargs)

    monkeypatch.setattr(TenantScopedRetriever, "_visible_document_ids", spy)
    return sizes


def install_synthetic_sources(
    monkeypatch, *, store, document_id: str, count: int = 40
) -> dict[str, list[int]]:
    """Replace both source searches with bounded synthetic candidate sets."""
    fetches: dict[str, list[int]] = {"vector": [], "lexical": []}

    async def scripted_vector(**kwargs):
        fetches["vector"].append(kwargs["top_k"])
        return synthetic(document_id, count, prefix="vec")[: kwargs["top_k"]]

    async def scripted_lexical(self, **kwargs):
        fetches["lexical"].append(kwargs["top_k"])
        return synthetic(document_id, count, prefix="lex")[: kwargs["top_k"]]

    monkeypatch.setattr(store, "search", scripted_vector)
    monkeypatch.setattr(SqlLexicalIndex, "search", scripted_lexical)
    return fetches


def hybrid_retriever(db, *, store, reranker=None, mode="hybrid") -> TenantScopedRetriever:
    return TenantScopedRetriever(
        db=db,
        embedder=HashingEmbeddingProvider(dimension=384),
        vector_store=store,
        reranker=reranker,
        lexical_index=SqlLexicalIndex(db),
        retrieval_mode=mode,
    )


# ------------------------------------------- 1: vector mode stays untouched
async def test_vector_mode_remains_unchanged(app, actor_factory, monkeypatch):
    app.state.settings.retrieval_mode = "vector"
    lexical_calls = install_lexical_spy(monkeypatch)

    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Policies")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="remote.txt",
        content=b"Remote work policy allows flextime on Fridays.",
    )

    response = await retrieve(client, session, query="remote work policy flextime")
    assert response.status_code == 200, response.text
    assert document_ids(response) == {document["id"]}
    assert lexical_calls == [], "vector mode must never run lexical search"
    assert set(response.json()[0]) == EXPECTED_FIELDS


# ------------------------------------- 2: hybrid runs each stage exactly once
async def test_hybrid_mode_executes_each_stage_exactly_once(app, actor_factory, monkeypatch):
    from app.services import rag

    lexical_calls = install_lexical_spy(monkeypatch)
    auth_sizes = install_auth_spy(monkeypatch)

    vector_calls: list[dict] = []
    store = app.state.vector_store
    original_store_search = store.search

    async def vector_spy(**kwargs):
        vector_calls.append(kwargs)
        return await original_store_search(**kwargs)

    monkeypatch.setattr(store, "search", vector_spy)

    embed_query_calls = {"count": 0}
    real_embedding_factory = rag.get_embedding_service

    class CountingEmbedder:
        def __init__(self, inner):
            self._inner = inner

        @property
        def dimension(self):
            return self._inner.dimension

        async def embed_query(self, text):
            embed_query_calls["count"] += 1
            return await self._inner.embed_query(text)

        async def embed_documents(self, texts):
            return await self._inner.embed_documents(texts)

    monkeypatch.setattr(
        "app.services.rag.get_embedding_service",
        lambda settings: CountingEmbedder(real_embedding_factory(settings)),
    )

    recorder = RecordingReranker()
    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: recorder)

    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="note.txt",
        content=b"Quarterly planning note for the engineering org.",
    )

    response = await retrieve(client, session, query="quarterly planning", top_k=10)
    assert response.status_code == 200, response.text
    assert response.json()

    assert len(vector_calls) == 1, "hybrid must query Qdrant exactly once"
    assert len(lexical_calls) == 1, "hybrid must query the lexical index exactly once"
    assert len(auth_sizes) == 1, "hybrid must authorize exactly once (the union)"
    assert embed_query_calls["count"] == 1, "hybrid must embed exactly once"
    assert len(recorder.calls) == 1, "hybrid must rerank exactly once"

    fetch_vector = vector_calls[0]["top_k"]
    fetch_lexical = lexical_calls[0]["top_k"]
    assert fetch_vector == fetch_lexical, "both sources share _initial_fetch sizing"
    assert fetch_vector <= MAX_CANDIDATES
    assert auth_sizes[0] <= 2 * MAX_CANDIDATES, "union is bounded by 2 x fetch"


# ------------------------------------------ 3: candidate only in lexical
async def test_lexical_only_candidate_reaches_results(app, actor_factory, monkeypatch):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    decoy = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="decoy.txt",
        content=b"Gardening tips for cucumbers and tomatoes.",
    )
    target = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="target.txt",
        content=b"Quantum entanglement notes for the physics lab.",
    )

    # the vector source only ever returns the decoy → the target can arrive
    # exclusively through the lexical source
    store = app.state.vector_store

    async def only_decoy(**kwargs):
        return [
            RetrievedChunk(
                text="gardening",
                score=0.9,
                document_id=decoy["id"],
                chunk_id="decoy-vec-0",
            )
        ]

    monkeypatch.setattr(store, "search", only_decoy)

    response = await retrieve(client, session, query="quantum entanglement notes")
    assert response.status_code == 200, response.text
    hits = response.json()
    ids = document_ids(response)
    assert target["id"] in ids, "the lexical-only candidate must surface"
    assert decoy["id"] in ids, "the scripted vector candidate is still returned"

    target_hit = next(hit for hit in hits if hit["documentId"] == target["id"])
    # lexical carrier: storage-only metadata, no vector payload hints
    assert set(target_hit["metadata"]) == {"chunk_index"}
    # lexical rank 1, vector absent → exactly one RRF contribution
    assert target_hit["score"] == pytest.approx(1 / (RRF_K + 1))


# ------------------------------------------ 4: candidate only in vector
async def test_vector_only_candidate_reaches_results(app, actor_factory, monkeypatch):
    async def no_lexical_candidates(self, **kwargs):
        return []

    monkeypatch.setattr(SqlLexicalIndex, "search", no_lexical_candidates)

    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="note.txt",
        content=b"Quarterly planning note for the engineering org.",
    )

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    hits = response.json()
    assert document_ids(response) == {document["id"]}

    hit = hits[0]
    # vector carrier keeps the vector payload metadata
    assert hit["metadata"]["tenant_id"] == tenant_of(session)
    # vector rank 1, lexical absent → exactly one RRF contribution
    assert hit["score"] == pytest.approx(1 / (RRF_K + 1))


# --------------------------------- 5: candidate present in both sources
async def test_chunk_in_both_sources_is_returned_once(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="note.txt",
        content=b"Quarterly planning note for the engineering org.",
    )

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    hits = response.json()

    chunk_ids = [hit["chunkId"] for hit in hits]
    assert len(chunk_ids) == len(set(chunk_ids)), "no duplicate chunk ids"
    assert document_ids(response) == {document["id"]}
    assert len(hits) == 1, "one chunk found by both sources is ONE result"
    # vector carrier survives deduplication
    assert "tenant_id" in hits[0]["metadata"]


# ------------------------------------------ 6: exact RRF calculation
def test_rrf_exact_formula_and_ordering():
    assert RRF_K == 60
    vector = [
        make_chunk("v1", score=0.99),
        make_chunk("v2", score=0.98),
        make_chunk("both", score=0.97),
    ]
    lexical = [make_chunk("both", score=12.5), make_chunk("l1", score=3.0)]

    fused = _rrf_fuse(_union_candidates(vector, lexical))
    scores = {candidate.chunk.chunk_id: candidate.fused_score for candidate in fused}

    # vector ranks: v1→1, v2→2, both→3; lexical ranks: both→1, l1→2
    assert scores["both"] == pytest.approx(1 / 63 + 1 / 61)
    assert scores["v1"] == pytest.approx(1 / 61)
    assert scores["v2"] == pytest.approx(1 / 62)
    assert scores["l1"] == pytest.approx(1 / 62)
    # fused DESC (0.0323, 0.0164, 0.0161, 0.0161); the v2/l1 tie at 1/62
    # is broken by vector presence (vector rank ASC, missing = +inf)
    assert [candidate.chunk.chunk_id for candidate in fused] == ["both", "v1", "v2", "l1"]


def test_rrf_edge_cases_empty_and_single_source():
    assert _union_candidates([], []) == []
    assert _rrf_fuse([]) == []

    only_lexical = _rrf_fuse(_union_candidates([], [make_chunk("l1"), make_chunk("l2")]))
    assert [c.chunk.chunk_id for c in only_lexical] == ["l1", "l2"]
    assert only_lexical[0].fused_score == pytest.approx(1 / 61)
    assert only_lexical[1].fused_score == pytest.approx(1 / 62)

    only_vector = _rrf_fuse(_union_candidates([make_chunk("v1"), make_chunk("v2")], []))
    assert [c.chunk.chunk_id for c in only_vector] == ["v1", "v2"]
    assert only_vector[0].fused_score == pytest.approx(1 / 61)


# --------------------------------------- 7: deterministic tie-breaking
def test_rrf_deterministic_tie_breaking():
    # equal fused score → vector presence sorts first (vector rank ASC,
    # missing = +inf), regardless of raw source scores
    vector = [make_chunk("vonly", score=0.5)]
    lexical = [make_chunk("lonly", score=0.001)]
    fused = _rrf_fuse(_union_candidates(vector, lexical))
    assert [c.chunk.chunk_id for c in fused] == ["vonly", "lonly"]

    # equal fused score AND vector ranks → lexical rank ASC decides
    first = _FusedCandidate(chunk=make_chunk("x1"), vector_rank=1, lexical_rank=3)
    second = _FusedCandidate(chunk=make_chunk("x2"), vector_rank=3, lexical_rank=1)
    assert first.fused_score == 0.0  # scores are computed by _rrf_fuse only
    ordered = _rrf_fuse([first, second])
    assert ordered[0].fused_score == ordered[1].fused_score
    assert [c.chunk.chunk_id for c in ordered] == ["x1", "x2"]

    # everything else equal → chunk_id ASC, independent of input order
    a = _FusedCandidate(chunk=make_chunk("zzz"), vector_rank=4, lexical_rank=7)
    b = _FusedCandidate(chunk=make_chunk("aaa"), vector_rank=4, lexical_rank=7)
    assert [c.chunk.chunk_id for c in _rrf_fuse([a, b])] == ["aaa", "zzz"]
    assert [c.chunk.chunk_id for c in _rrf_fuse([b, a])] == ["aaa", "zzz"]


# ------------------------------------------ 8: deduplication by chunk_id
def test_deduplication_by_chunk_id_retains_both_source_ranks():
    vector = [make_chunk("dup", score=0.9), make_chunk("only-v", score=0.8)]
    lexical = [make_chunk("dup", score=7.0), make_chunk("only-l", score=2.0)]

    union = _union_candidates(vector, lexical)
    assert len(union) == 3, "one shared chunk_id collapses to one candidate"

    by_id = {candidate.chunk.chunk_id: candidate for candidate in union}
    dup = by_id["dup"]
    assert dup.vector_rank == 1 and dup.lexical_rank == 1
    assert dup.vector_score == 0.9 and dup.lexical_score == 7.0
    assert dup.chunk is vector[0], "vector chunk is the carrier when present"
    assert by_id["only-v"].lexical_rank is None
    assert by_id["only-l"].vector_rank is None
    assert by_id["only-l"].chunk is lexical[1], "lexical-only keeps its carrier"
    # private source data never leaks into the public chunk
    assert not hasattr(dup.chunk, "vector_rank")
    assert not hasattr(dup.chunk, "lexical_rank")


def test_duplicate_ids_within_one_source_keep_the_first_rank():
    """A repeated id must never downgrade its own source rank."""
    vector = [
        make_chunk("dup-v", score=0.9, text="best vector occurrence"),
        make_chunk("dup-v", score=0.1, text="later duplicate"),
        make_chunk("v-only", score=0.8),
    ]
    lexical = [
        make_chunk("dup-l", score=9.0),
        make_chunk("dup-l", score=1.0),
        make_chunk("l-only", score=2.0),
    ]

    by_id = {
        candidate.chunk.chunk_id: candidate
        for candidate in _union_candidates(vector, lexical)
    }
    assert set(by_id) == {"dup-v", "v-only", "dup-l", "l-only"}
    assert by_id["dup-v"].vector_rank == 1
    assert by_id["dup-v"].vector_score == 0.9
    assert by_id["dup-v"].chunk is vector[0]
    assert by_id["dup-l"].lexical_rank == 1
    assert by_id["dup-l"].lexical_score == 9.0
    assert by_id["dup-l"].chunk is lexical[0]


# ------------------------------------------ 9: tenant isolation
async def test_hybrid_tenant_isolation(app, actor_factory):
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    collection_a = await create_collection(client_a, session_a, name="Acme Files")
    collection_b = await create_collection(client_b, session_b, name="Globex Files")
    doc_a = await upload(
        client_a,
        session_a,
        collection_id=collection_a["id"],
        filename="a.txt",
        content=b"Acme secret merger documents describe the acquisition timeline.",
    )
    doc_b = await upload(
        client_b,
        session_b,
        collection_id=collection_b["id"],
        filename="b.txt",
        content=b"Acme secret merger documents describe the acquisition timeline.",
    )

    response_a = await retrieve(client_a, session_a, query="secret merger documents")
    assert document_ids(response_a) == {doc_a["id"]}
    assert doc_b["id"] not in document_ids(response_a)

    response_b = await retrieve(client_b, session_b, query="secret merger documents")
    assert document_ids(response_b) == {doc_b["id"]}
    assert doc_a["id"] not in document_ids(response_b)


# ------------------------------------------ 10: collection filtering
async def test_hybrid_collection_filtering(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    col_one = await create_collection(client, session, name="One")
    col_two = await create_collection(client, session, name="Two")
    doc_one = await upload(
        client,
        session,
        collection_id=col_one["id"],
        filename="one.txt",
        content=b"Budget forecast numbers for next year.",
    )
    doc_two = await upload(
        client,
        session,
        collection_id=col_two["id"],
        filename="two.txt",
        content=b"Budget forecast numbers for next year.",
    )

    async with app.state.session_factory() as db:
        retriever = hybrid_retriever(db, store=app.state.vector_store)
        only_one = await retriever.retrieve(
            query="budget forecast numbers",
            tenant_id=tenant_of(session),
            user_id=session["user"]["id"],
            collection_ids=[col_one["id"]],
            top_k=10,
        )
        unfiltered = await retriever.retrieve(
            query="budget forecast numbers",
            tenant_id=tenant_of(session),
            user_id=session["user"]["id"],
            top_k=10,
        )

    assert {chunk.document_id for chunk in only_one} == {doc_one["id"]}
    assert {chunk.document_id for chunk in unfiltered} == {doc_one["id"], doc_two["id"]}


# --------------------------------- 11: permission grant (no re-ingestion)
async def test_hybrid_permission_grant_without_reingestion(app, actor_factory):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    member_client, member_session = await actor_factory(
        name="Mia Member",
        email="mia@acme.com",
        invited_by=(owner_client, owner_session),
        role="member",
    )
    member_id = member_session["user"]["id"]
    collection = await create_collection(owner_client, owner_session, name="HR")
    document = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="salary.txt",
        content=b"Salary band revision details for senior engineers in 2026.",
        classification="confidential",
    )

    before = await retrieve(member_client, member_session, query="salary band revision")
    assert document_ids(before) == set()

    granted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": [member_id]},
        headers=auth(owner_session),
    )
    assert granted.status_code == 200, granted.text

    during = await retrieve(member_client, member_session, query="salary band revision")
    assert document_ids(during) == {document["id"]}


# --------------------------------- 12: permission revoke (no re-ingestion)
async def test_hybrid_permission_revoke_without_reingestion(app, actor_factory):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    member_client, member_session = await actor_factory(
        name="Mia Member",
        email="mia@acme.com",
        invited_by=(owner_client, owner_session),
        role="member",
    )
    member_id = member_session["user"]["id"]
    collection = await create_collection(owner_client, owner_session, name="HR")
    document = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="salary.txt",
        content=b"Salary band revision details for senior engineers in 2026.",
        classification="confidential",
    )
    granted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": [member_id]},
        headers=auth(owner_session),
    )
    assert granted.status_code == 200, granted.text
    visible = await retrieve(member_client, member_session, query="salary band revision")
    assert document_ids(visible) == {document["id"]}

    revoked = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": []},
        headers=auth(owner_session),
    )
    assert revoked.status_code == 200, revoked.text
    after = await retrieve(member_client, member_session, query="salary band revision")
    assert document_ids(after) == set(), "revocation applies immediately, no re-ingest"


# ------------------------------------------ 13: role rules
async def test_hybrid_applies_current_role_rules(app, actor_factory):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    viewer_client, viewer_session = await actor_factory(
        name="Vic Viewer",
        email="vic@acme.com",
        invited_by=(owner_client, owner_session),
        role="viewer",
    )
    collection = await create_collection(owner_client, owner_session, name="Mixed")
    internal = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="handbook.txt",
        content=b"Onboarding handbook for all new employees this quarter.",
        classification="internal",
    )
    confidential = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="board.txt",
        content=b"Onboarding handbook for all new employees this quarter.",
        classification="confidential",
    )

    owner_ids = document_ids(
        await retrieve(owner_client, owner_session, query="onboarding handbook")
    )
    assert owner_ids == {internal["id"], confidential["id"]}

    viewer_response = await retrieve(
        viewer_client, viewer_session, query="onboarding handbook"
    )
    assert viewer_response.status_code == 200, viewer_response.text
    viewer_ids = document_ids(viewer_response)
    assert viewer_ids == {internal["id"]}
    assert confidential["id"] not in viewer_ids


# ------------------------- 14: unauthorized candidates never reach reranker
async def test_unauthorized_candidates_never_reach_hybrid_reranker(
    app, actor_factory, monkeypatch
):
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
    outsider_collection = await create_collection(
        outsider_client, outsider_session, name="Files"
    )

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
        content=b"salary band revision for everyone in the org today",
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
    assert document_ids(response) == {shared["id"]}


# ------------------------- 15: union ≤ 80, authorized in exactly one call
async def test_hybrid_union_is_bounded_and_authorized_once(app, actor_factory, monkeypatch):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="doc.txt",
        content=b"Shared quarterly planning content.",
    )

    # top_k=14 → _initial_fetch = min(min(42, 40), ...) = 40 per source
    fetches = install_synthetic_sources(
        monkeypatch, store=app.state.vector_store, document_id=document["id"], count=40
    )
    auth_sizes = install_auth_spy(monkeypatch)
    recorder = RecordingReranker()
    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: recorder)

    response = await retrieve(client, session, query="quarterly planning", top_k=14)
    assert response.status_code == 200, response.text

    assert fetches["vector"] == [40], "vector fetch capped at MAX_CANDIDATES"
    assert fetches["lexical"] == [40], "lexical fetch capped at MAX_CANDIDATES"
    assert auth_sizes == [2 * 40], "ONE authorization call over the ≤ 80 union"
    # existing reranker pool cap: never above RERANKER_MAX_CANDIDATES (40)
    assert len(recorder.calls[0]) <= 40


# ------------------------- 16: reranker receives ≤ 40 fused candidates
async def test_hybrid_reranker_pool_capped_at_existing_limit(app, actor_factory, monkeypatch):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="doc.txt",
        content=b"Shared quarterly planning content.",
    )

    install_synthetic_sources(
        monkeypatch, store=app.state.vector_store, document_id=document["id"], count=40
    )
    recorder = RecordingReranker()
    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: recorder)

    response = await retrieve(client, session, query="quarterly planning", top_k=14)
    assert response.status_code == 200, response.text

    pool = recorder.calls[0]
    assert len(pool) == 40, "80 authorized candidates → existing 40-candidate cap"
    assert all(
        0.0 < chunk.score <= 1.0 / (RRF_K + 1) for chunk in pool
    ), "the reranker sees fused RRF scores, never raw source scores"


# ------------------------- 17: final ≤ min(top_k, rerank_top_k)
async def test_hybrid_final_result_respects_reranker_top_k(app, actor_factory, monkeypatch):
    app.state.settings.reranker_top_k = 3
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="doc.txt",
        content=b"Shared quarterly planning content.",
    )
    install_synthetic_sources(
        monkeypatch, store=app.state.vector_store, document_id=document["id"], count=10
    )

    response = await retrieve(client, session, query="quarterly planning", top_k=10)
    assert response.status_code == 200, response.text
    hits = response.json()
    assert len(hits) == 3  # RERANKER_TOP_K, never more than requested


# ------------------------------------------ 18: vector failure → 503
async def test_hybrid_vector_failure_returns_503(app, actor_factory, monkeypatch):
    class ExplodingStore:
        async def search(self, **kwargs):
            raise RuntimeError("qdrant at 127.0.0.1:6333 exploded with api_key=sk-LEAK")

        async def upsert_chunks(self, **kwargs):  # pragma: no cover - unused
            raise NotImplementedError

        async def delete_document(self, **kwargs):  # pragma: no cover - unused
            raise NotImplementedError

    monkeypatch.setattr(app.state, "vector_store", ExplodingStore())
    recorder = RecordingReranker()
    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: recorder)

    client, session = await actor_factory(name="Fail", email="fail@example.com", org="Ops")
    response = await retrieve(client, session, query="anything")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert recorder.calls == [], "a failed source must not reach the reranker"
    body = response.text.lower()
    assert "sk-leak" not in body
    assert "127.0.0.1" not in body
    assert "traceback" not in body


# ------------------------------------------ 19: lexical failure → 503
async def test_hybrid_lexical_failure_returns_503(app, actor_factory, monkeypatch):
    async def exploding_lexical(self, **kwargs):
        raise RuntimeError("postgres exploded with password=sk-DB-LEAK")

    monkeypatch.setattr(SqlLexicalIndex, "search", exploding_lexical)
    recorder = RecordingReranker()
    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: recorder)

    client, session = await actor_factory(name="Fail", email="fail2@example.com", org="Ops")
    response = await retrieve(client, session, query="anything")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert recorder.calls == [], "a failed source must not reach the reranker"
    body = response.text.lower()
    assert "sk-db-leak" not in body
    assert "traceback" not in body


# ------------------------------------------ 20: reranker failure → 503
async def test_hybrid_reranker_failure_returns_503(app, actor_factory, monkeypatch):
    client, session = await actor_factory(name="Fail", email="fail3@example.com", org="Ops")
    collection = await create_collection(client, session, name="Docs")
    await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="doc.txt",
        content=b"Quarterly planning note.",
    )

    monkeypatch.setattr("app.services.rag.get_reranker", lambda settings: ExplodingReranker())
    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    body = response.text.lower()
    assert "sk-rerank-leak" not in body
    assert "traceback" not in body


# ------------------------------------------ 21: default mode stays vector
def test_default_retrieval_mode_is_vector():
    assert Settings(_env_file=None).retrieval_mode == "vector"

    vector_retriever = get_retriever(Settings(_env_file=None), db=object(), vector_store=object())
    assert vector_retriever.retrieval_mode == "vector"

    hybrid_settings = Settings(_env_file=None, retrieval_mode="hybrid")
    hybrid_retriever_from_settings = get_retriever(
        hybrid_settings, db=object(), vector_store=object()
    )
    assert hybrid_retriever_from_settings.retrieval_mode == "hybrid"


def test_unknown_internal_mode_fails_safely():
    with pytest.raises(ValueError, match="retrieval_mode"):
        TenantScopedRetriever(
            db=None,  # type: ignore[arg-type]
            embedder=None,  # type: ignore[arg-type]
            vector_store=None,  # type: ignore[arg-type]
            retrieval_mode="banana",
        )
    normalized = TenantScopedRetriever(
        db=None,  # type: ignore[arg-type]
        embedder=None,  # type: ignore[arg-type]
        vector_store=None,  # type: ignore[arg-type]
        retrieval_mode="  Hybrid  ",
    )
    assert normalized.retrieval_mode == "hybrid"


# ------------------------- 22: client cannot activate hybrid via body
async def test_client_cannot_select_retrieval_mode(app, actor_factory, monkeypatch):
    app.state.settings.retrieval_mode = "vector"
    lexical_calls = install_lexical_spy(monkeypatch)

    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="note.txt",
        content=b"Quarterly planning note for the engineering org.",
    )

    response = await retrieve(
        client,
        session,
        query="quarterly planning",
        retrievalMode="hybrid",  # ignored: not part of the schema
        mode="hybrid",  # ignored as well: mode is server-side configuration
    )
    assert response.status_code == 200, response.text
    assert document_ids(response) == {document["id"]}
    assert lexical_calls == [], "body hints must not activate the hybrid path"


# ------------------------- 23: response shape unchanged in hybrid mode
async def test_hybrid_response_fields_remain_unchanged(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="note.txt",
        content=b"Quarterly planning note for the engineering org.",
    )

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    hits = response.json()
    assert set(hits[0]) == EXPECTED_FIELDS
    assert isinstance(hits[0]["score"], float)
    assert isinstance(hits[0]["rerankScore"], float)
    # hybrid score = fused RRF of the single chunk from both sources
    assert hits[0]["score"] == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 1))


# ------------------------- 24: empty vector source is not a failure
async def test_hybrid_empty_vector_source_returns_lexical_results(
    app, actor_factory, monkeypatch
):
    async def no_vector_candidates(**kwargs):
        return []

    monkeypatch.setattr(app.state.vector_store, "search", no_vector_candidates)

    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="note.txt",
        content=b"Quarterly planning note for the engineering org.",
    )

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    assert document_ids(response) == {document["id"]}
    hit = response.json()[0]
    assert hit["score"] == pytest.approx(1 / (RRF_K + 1))  # lexical rank 1 only
    assert "tenant_id" not in hit["metadata"]  # lexical carrier


# ------------------------- 25: empty lexical source is not a failure
async def test_hybrid_empty_lexical_source_returns_vector_results(
    app, actor_factory, monkeypatch
):
    async def no_lexical_candidates(self, **kwargs):
        return []

    monkeypatch.setattr(SqlLexicalIndex, "search", no_lexical_candidates)

    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="note.txt",
        content=b"Quarterly planning note for the engineering org.",
    )

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    assert document_ids(response) == {document["id"]}
    hit = response.json()[0]
    assert hit["score"] == pytest.approx(1 / (RRF_K + 1))  # vector rank 1 only
    assert hit["metadata"]["tenant_id"] == tenant_of(session)  # vector carrier


# ------------------------- 26: both sources empty → clean empty list
async def test_hybrid_both_sources_empty_returns_empty_list(
    app, actor_factory, monkeypatch
):
    async def no_vector_candidates(**kwargs):
        return []

    async def no_lexical_candidates(self, **kwargs):
        return []

    monkeypatch.setattr(app.state.vector_store, "search", no_vector_candidates)
    monkeypatch.setattr(SqlLexicalIndex, "search", no_lexical_candidates)

    client, session = await actor_factory(name="Zoe", email="zoe@example.com", org="Empty Co")
    response = await retrieve(client, session, query="anything at all")
    assert response.status_code == 200, response.text
    assert response.json() == []


# ------------------------- 27: hybrid + no lexical index → 501
@pytest.mark.parametrize(
    "null_index", [None, NullLexicalIndex()], ids=["no-index", "null-index"]
)
async def test_hybrid_without_lexical_index_fails_501(app, actor_factory, null_index):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")

    async with app.state.session_factory() as db:
        retriever = TenantScopedRetriever(
            db=db,
            embedder=HashingEmbeddingProvider(dimension=384),
            vector_store=app.state.vector_store,
            lexical_index=null_index,
            retrieval_mode="hybrid",
        )
        with pytest.raises(AppError) as excinfo:
            await retriever.retrieve(
                query="anything at all",
                tenant_id=tenant_of(session),
                user_id=session["user"]["id"],
            )
    assert excinfo.value.code == "SERVICE_NOT_CONFIGURED"
    assert excinfo.value.status_code == 501


async def test_hybrid_endpoint_fails_501_without_lexical_index(
    app, actor_factory, monkeypatch
):
    monkeypatch.setattr(
        "app.services.rag.get_lexical_index",
        lambda settings, db=None: NullLexicalIndex(),
    )
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    response = await retrieve(client, session, query="anything at all")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "SERVICE_NOT_CONFIGURED"


# ------------------------- 28: duplicate chunk gets BOTH contributions
def test_duplicate_chunk_gets_both_rrf_contributions():
    vector = [make_chunk("dup", score=0.42)]
    lexical = [make_chunk("dup", score=9.9)]

    union = _union_candidates(vector, lexical)
    assert len(union) == 1

    fused = _rrf_fuse(union)
    assert len(fused) == 1
    candidate = fused[0]
    assert candidate.vector_rank == 1
    assert candidate.lexical_rank == 1
    assert candidate.fused_score == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 1))
    # raw scores (0.42 / 9.9) never appear in the fused value
    assert candidate.fused_score < 0.04


async def test_chunk_in_both_sources_scores_two_rrf_contributions(
    app, actor_factory
):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="note.txt",
        content=b"Quarterly planning note for the engineering org.",
    )

    response = await retrieve(client, session, query="quarterly planning")
    assert response.status_code == 200, response.text
    hit = response.json()[0]
    assert hit["score"] == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 1))


# ------------------------- 29: raw source scores are NEVER used
def test_rrf_never_uses_raw_source_scores():
    # wildly different raw scores, identical ranks → identical fused scores
    vector = [make_chunk("vhigh", score=0.999999)]
    lexical = [make_chunk("ltiny", score=1e-9)]
    fused = _rrf_fuse(_union_candidates(vector, lexical))
    assert len(fused) == 2
    for candidate in fused:
        assert candidate.fused_score == pytest.approx(1 / (RRF_K + 1))
    assert all(candidate.fused_score < 0.02 for candidate in fused)

    # lexical rank 1 with a near-zero raw score beats vector rank 2 with a
    # near-perfect raw score — only ranks decide
    vector = [make_chunk("vdecoy", score=0.99), make_chunk("vsecond", score=0.98)]
    lexical = [make_chunk("ltiny", score=1e-9)]
    ordered = [c.chunk.chunk_id for c in _rrf_fuse(_union_candidates(vector, lexical))]
    assert ordered == ["vdecoy", "ltiny", "vsecond"]


# ------------------------- 30: deterministic across execution
def test_rrf_ordering_stable_across_runs():
    vector = [make_chunk(f"v{index}") for index in range(5)]
    lexical = [make_chunk(f"l{index}") for index in range(5)]

    def run() -> list[str]:
        return [c.chunk.chunk_id for c in _rrf_fuse(_union_candidates(vector, lexical))]

    first = run()
    second = run()
    assert first == second
    assert len(first) == 10


async def test_hybrid_responses_are_deterministic(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    for index in range(3):
        await upload(
            client,
            session,
            collection_id=collection["id"],
            filename=f"doc{index}.txt",
            content=f"Quarterly planning note number {index}.".encode(),
        )

    first = await retrieve(client, session, query="quarterly planning", top_k=3)
    second = await retrieve(client, session, query="quarterly planning", top_k=3)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    first_ids = [hit["chunkId"] for hit in first.json()]
    second_ids = [hit["chunkId"] for hit in second.json()]
    assert first_ids == second_ids
    assert [hit["score"] for hit in first.json()] == [hit["score"] for hit in second.json()]


# ------------------------- 31: hidden candidate never shifts visible ranks (M-2)
async def test_hidden_candidate_never_shifts_visible_rank_scores(
    app, actor_factory, monkeypatch
):
    """Ranks come from the AUTHORIZED set, never from the raw fetch order."""
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    member_client, member_session = await actor_factory(
        name="Mia Member",
        email="mia@acme.com",
        invited_by=(owner_client, owner_session),
        role="member",
    )
    collection = await create_collection(owner_client, owner_session, name="Archive")
    doc_a = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Quokka Field Notes.pdf",
        classification="internal",
    )
    doc_x = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Quokka Confidential Dossier.pdf",
        classification="confidential",
    )
    doc_b = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Quokka Summary.pdf",
        classification="internal",
    )

    async def scripted_vector(**kwargs):
        return [
            make_chunk("vec-a", document_id=doc_a["id"], text="field notes"),
            make_chunk("vec-x", document_id=doc_x["id"], text="confidential dossier"),
            make_chunk("vec-b", document_id=doc_b["id"], text="summary"),
        ]

    async def no_lexical(self, **kwargs):
        return []

    monkeypatch.setattr(app.state.vector_store, "search", scripted_vector)
    monkeypatch.setattr(SqlLexicalIndex, "search", no_lexical)

    member_response = await retrieve(member_client, member_session, query="quokka archive")
    assert member_response.status_code == 200, member_response.text
    member_scores = {hit["documentId"]: hit["score"] for hit in member_response.json()}
    # doc_x (fetch rank 2) is hidden from the member: doc_b sits at
    # AUTHORIZED rank 2, so its score is 1/62 — never the fetch-rank
    # side-channel 1/63 that would reveal how many hidden rows precede it
    assert set(member_scores) == {doc_a["id"], doc_b["id"]}
    assert member_scores[doc_a["id"]] == pytest.approx(1 / (RRF_K + 1))
    assert member_scores[doc_b["id"]] == pytest.approx(1 / (RRF_K + 2))

    owner_response = await retrieve(owner_client, owner_session, query="quokka archive")
    assert owner_response.status_code == 200, owner_response.text
    owner_scores = {hit["documentId"]: hit["score"] for hit in owner_response.json()}
    # the owner may see doc_x, so doc_b legitimately sits at rank 3
    assert set(owner_scores) == {doc_a["id"], doc_x["id"], doc_b["id"]}
    assert owner_scores[doc_a["id"]] == pytest.approx(1 / (RRF_K + 1))
    assert owner_scores[doc_x["id"]] == pytest.approx(1 / (RRF_K + 2))
    assert owner_scores[doc_b["id"]] == pytest.approx(1 / (RRF_K + 3))


# ------------------------- 32: ranks recomputed over authorized set only (M-2)
def test_hidden_candidate_removed_before_rank_computation():
    vector = [
        make_chunk("hidden", document_id="doc-hidden"),
        make_chunk("a1", document_id="doc-a"),
        make_chunk("a2", document_id="doc-a"),
    ]
    union = _union_candidates(vector, [])
    authorized = [candidate for candidate in union if candidate.chunk.chunk_id != "hidden"]

    fused = _rrf_fuse(_recompute_source_ranks(authorized))
    scores = {candidate.chunk.chunk_id: candidate.fused_score for candidate in fused}
    assert scores["a1"] == pytest.approx(1 / (RRF_K + 1))
    assert scores["a2"] == pytest.approx(1 / (RRF_K + 2))

    # the stored fetch ranks still encode the hidden candidate — fusing them
    # WITHOUT the recompute would expose 1/62 for a1 instead of 1/61
    leaky = _rrf_fuse(authorized)
    leaky_scores = {candidate.chunk.chunk_id: candidate.fused_score for candidate in leaky}
    assert leaky_scores["a1"] == pytest.approx(1 / (RRF_K + 2))
    assert scores["a1"] != pytest.approx(leaky_scores["a1"])


# ---------------- 33: recompute is independent across sources (M-2)
def test_rank_recompute_is_independent_of_hidden_cross_source_candidates():
    vector = [make_chunk("h-vec"), make_chunk("vis-1"), make_chunk("vis-2")]
    lexical = [make_chunk("h-lex"), make_chunk("vis-2"), make_chunk("vis-1")]
    hidden = {"h-vec", "h-lex"}

    union = _union_candidates(vector, lexical)
    authorized = [candidate for candidate in union if candidate.chunk.chunk_id not in hidden]
    with_hidden = _rrf_fuse(_recompute_source_ranks(authorized))

    visible_only = _rrf_fuse(
        _recompute_source_ranks(
            _union_candidates(
                [chunk for chunk in vector if chunk.chunk_id not in hidden],
                [chunk for chunk in lexical if chunk.chunk_id not in hidden],
            )
        )
    )

    # a hidden candidate in either source never moves the visible candidates
    assert [(c.chunk.chunk_id, c.fused_score) for c in with_hidden] == [
        (c.chunk.chunk_id, c.fused_score) for c in visible_only
    ]
    scores = {candidate.chunk.chunk_id: candidate.fused_score for candidate in with_hidden}
    assert scores["vis-1"] == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 2))
    assert scores["vis-2"] == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))


# ------------------------- 34: recompute never mutates its input (M-2)
def test_recompute_returns_new_instances_and_preserves_inputs():
    vector = [make_chunk("hidden"), make_chunk("v1"), make_chunk("v2")]
    lexical = [make_chunk("v2"), make_chunk("l1")]
    union = _union_candidates(vector, lexical)
    snapshot = [(c.chunk.chunk_id, c.vector_rank, c.lexical_rank) for c in union]

    authorized = [candidate for candidate in union if candidate.chunk.chunk_id != "hidden"]
    recomputed = _recompute_source_ranks(authorized)

    assert all(
        new is not old
        for new, old in zip(recomputed, authorized, strict=True)
    )
    assert [(c.chunk.chunk_id, c.vector_rank, c.lexical_rank) for c in union] == snapshot
    assert [c.chunk.chunk_id for c in recomputed] == [c.chunk.chunk_id for c in authorized]

    by_id = {candidate.chunk.chunk_id: candidate for candidate in recomputed}
    # dense renumbering over the authorized set: v1 was fetch rank 2 → rank 1
    assert by_id["v1"].vector_rank == 1
    assert by_id["v1"].lexical_rank is None
    assert by_id["v2"].vector_rank == 2
    assert by_id["v2"].lexical_rank == 1
    # sources the candidate never appeared in stay None
    assert by_id["l1"].vector_rank is None
    assert by_id["l1"].lexical_rank == 2


# ------------------------- 35: recompute + fusion stay deterministic (M-2)
def test_rank_recompute_and_fusion_are_deterministic():
    vector = [make_chunk(f"v{index}") for index in range(4)]
    lexical = [make_chunk(f"l{index}") for index in range(4)]

    def run() -> list[tuple[str, float]]:
        union = _union_candidates(vector, lexical)
        authorized = [candidate for candidate in union if candidate.chunk.chunk_id != "v0"]
        fused = _rrf_fuse(_recompute_source_ranks(authorized))
        return [(candidate.chunk.chunk_id, candidate.fused_score) for candidate in fused]

    first = run()
    second = run()
    assert first == second
    assert len(first) == 7  # 8 deduplicated candidates minus the hidden one
    assert dict(first)["v1"] == pytest.approx(1 / (RRF_K + 1))
