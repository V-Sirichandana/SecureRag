"""Milestone 3: tenant-scoped lexical search — FTS5 behavior + PG construction.

What is under test:

* candidate generation: ranking, deterministic tiebreak, score normalization
  (> 0, higher-is-better), complete ``RetrievedChunk`` mapping;
* fencing: tenant isolation, optional collection filter, malformed ids fail
  closed — the SQL fence is NOT an authorization layer, so the CURRENT
  database permissions are enforced separately through
  ``TenantScopedRetriever.retrieve_lexical`` (grant/revoke lifecycle, roles,
  reranker-spy boundary);
* bounds: unusable ``top_k`` yields nothing, results never exceed
  ``MAX_TOP_K``;
* hostile input: quotes/``*``/``(`/``OR``/column selectors can never raise;
* read-only guarantees: no flush, no commit, no DDL (a database without the
  FTS mirror simply yields ``[]``);
* vector-mode regression: the public ``retrieve()`` path never calls
  ``SqlLexicalIndex.search``;
* PostgreSQL branch: asserted at SQL-construction level only — this
  environment has no PostgreSQL service, so these are NOT (and do not fake)
  integration tests. The FTS5 branch runs against the real SQLite database.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.config import Settings
from app.core.exceptions import AppError, AuthorizationError
from app.db.database import create_all, drop_all
from app.main import create_app
from app.models.document import DocumentChunk
from app.services.ingestion.embeddings import HashingEmbeddingProvider
from app.services.rag.lexical import (
    NullLexicalIndex,
    SqlLexicalIndex,
    _bounded_fetch,
    _fts_tokens,
    postgres_search_statement,
)
from app.services.rag.retriever import MAX_TOP_K, TenantScopedRetriever
from tests.conftest import auth, create_collection
from tests.test_retrieval import document_ids, retrieve, tenant_of, upload
from tests.test_retrieval_rerank import RecordingReranker

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


# ------------------------------------------------------------------ helpers
async def search_direct(
    app,
    *,
    tenant_id: str,
    query: str,
    collection_ids: list[str] | None = None,
    top_k: int = 8,
) -> list:
    async with app.state.session_factory() as db:
        return await SqlLexicalIndex(db).search(
            query=query,
            tenant_id=tenant_id,
            collection_ids=collection_ids,
            top_k=top_k,
        )


async def seed_chunks(
    app,
    *,
    tenant_id: str,
    document_id: str,
    collection_id: str,
    filename: str,
    texts: list[str],
    chunk_index_start: int = 0,
    page: int = 1,
) -> list[str]:
    """Replace a document's lexical rows with exactly controlled payloads."""
    payloads = [
        {
            "chunk_id": f"{filename}-{index:03d}",
            "text": text,
            "chunk_index": chunk_index_start + index,
            "page": page,
            "filename": filename,
            "collection_id": collection_id,
        }
        for index, text in enumerate(texts)
    ]
    async with app.state.session_factory() as db:
        await SqlLexicalIndex(db).replace_document(
            tenant_id=tenant_id,
            document_id=document_id,
            payloads=payloads,
        )
        await db.commit()
    return [payload["chunk_id"] for payload in payloads]


def lexical_retriever(db, *, reranker=None) -> TenantScopedRetriever:
    return TenantScopedRetriever(
        db=db,
        embedder=HashingEmbeddingProvider(dimension=32),
        vector_store=None,  # type: ignore[arg-type] - retrieve_lexical never embeds
        reranker=reranker,
        lexical_index=SqlLexicalIndex(db),
    )


async def lexical_document_ids(app, *, session: dict, query: str, **kwargs) -> set[str]:
    async with app.state.session_factory() as db:
        results = await lexical_retriever(db).retrieve_lexical(
            query=query,
            tenant_id=tenant_of(session),
            user_id=session["user"]["id"],
            **kwargs,
        )
    return {chunk.document_id for chunk in results}


# -------------------------------------------------- sanitizer + bound units
def test_tokens_drop_syntax_and_operators():
    assert _fts_tokens("plain words") == ["plain", "words"]
    assert _fts_tokens('"quoted (stars) * col:value"') == [
        "quoted",
        "stars",
        "col",
        "value",
    ]
    assert _fts_tokens("a AND b OR c NOT d") == ["a", "b", "c", "d"]
    assert _fts_tokens("   ") == []
    assert _fts_tokens("🙂🙂") == []
    assert _fts_tokens("mixed123 unicodeÜ") == ["mixed123", "unicodeÜ"]


@pytest.mark.parametrize(
    ("top_k", "expected"),
    [(8, 8), (1, 1), (MAX_TOP_K, MAX_TOP_K), (MAX_TOP_K + 1, MAX_TOP_K),
     (9999, MAX_TOP_K), (0, None), (-1, None), ("abc", None), (None, None)],
)
def test_bounded_fetch_clamps_or_refuses(top_k, expected):
    assert _bounded_fetch(top_k) == expected


# ------------------------------------- ranking + scores + mapping (FTS5 real)
async def test_bm25_ranking_scores_and_mapping(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    tenant = tenant_of(session)

    strong = await upload(
        client, session,
        collection_id=collection["id"], filename="strong.txt",
        content=b"placeholder for seeding one.",
    )
    weak = await upload(
        client, session,
        collection_id=collection["id"], filename="weak.txt",
        content=b"placeholder for seeding two.",
    )
    absent = await upload(
        client, session,
        collection_id=collection["id"], filename="absent.txt",
        content=b"placeholder for seeding three.",
    )

    # identical document length, five vs one occurrence of the query term
    await seed_chunks(
        app, tenant_id=tenant, document_id=strong["id"],
        collection_id=collection["id"], filename="strong.txt",
        texts=["quantum quantum quantum quantum quantum computing lab"],
    )
    await seed_chunks(
        app, tenant_id=tenant, document_id=weak["id"],
        collection_id=collection["id"], filename="weak.txt",
        texts=["quantum computing lab equipment service schedule"],
    )
    await seed_chunks(
        app, tenant_id=tenant, document_id=absent["id"],
        collection_id=collection["id"], filename="absent.txt",
        texts=["gardening advice for the weekend only today"],
    )

    results = await search_direct(app, tenant_id=tenant, query="quantum", top_k=10)

    assert [chunk.document_id for chunk in results] == [strong["id"], weak["id"]]
    assert absent["id"] not in {chunk.document_id for chunk in results}

    # scores: strictly positive, higher-is-better, non-increasing by rank
    assert all(chunk.score > 0 for chunk in results)
    assert results[0].score > results[1].score
    assert all(
        results[index].score >= results[index + 1].score
        for index in range(len(results) - 1)
    )

    # complete mapping from the canonical row
    hit = results[0]
    assert hit.text == "quantum quantum quantum quantum quantum computing lab"
    assert hit.document_id == strong["id"]
    assert hit.collection_id == collection["id"]
    assert hit.chunk_id == "strong.txt-000"
    assert hit.page_number == 1
    assert hit.filename == "strong.txt"
    assert hit.quote == hit.text[:200]
    assert hit.rerank_score is None
    assert hit.metadata == {"chunk_index": 0}  # storage-only: no authz hints
    for forbidden in ("tenant_id", "created_by", "access", "classification"):
        assert forbidden not in hit.metadata


async def test_identical_chunks_tiebreak_by_chunk_id(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    tenant = tenant_of(session)

    doc_a = await upload(
        client, session, collection_id=collection["id"],
        filename="a.txt", content=b"placeholder a.",
    )
    doc_b = await upload(
        client, session, collection_id=collection["id"],
        filename="b.txt", content=b"placeholder b.",
    )
    text = "tied ranking content sample"
    await seed_chunks(
        app, tenant_id=tenant, document_id=doc_a["id"],
        collection_id=collection["id"], filename="zzz", texts=[text],
    )
    await seed_chunks(
        app, tenant_id=tenant, document_id=doc_b["id"],
        collection_id=collection["id"], filename="aaa", texts=[text],
    )

    results = await search_direct(app, tenant_id=tenant, query="tied ranking")
    chunk_ids = [chunk.chunk_id for chunk in results]

    assert chunk_ids == sorted(chunk_ids)  # deterministic chunk_id ASC tiebreak
    assert chunk_ids == ["aaa-000", "zzz-000"]
    assert results[0].score == results[1].score  # identical text → identical bm25


async def test_mapping_truncates_quote_and_keeps_chunk_index(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    tenant = tenant_of(session)
    document = await upload(
        client, session, collection_id=collection["id"],
        filename="up.txt", content=b"placeholder.",
    )
    long_text = "quotetest " + ("x" * 400)
    await seed_chunks(
        app, tenant_id=tenant, document_id=document["id"],
        collection_id=collection["id"], filename="report.pdf",
        texts=[long_text], chunk_index_start=7, page=3,
    )

    results = await search_direct(app, tenant_id=tenant, query="quotetest")

    assert len(results) == 1
    hit = results[0]
    assert hit.text == long_text
    assert hit.quote == long_text[:200]
    assert hit.page_number == 3
    assert hit.filename == "report.pdf"
    assert hit.metadata == {"chunk_index": 7}


# ------------------------------------------------------------------ fencing
async def test_tenant_fence_returns_only_own_chunks(app, actor_factory):
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    collection_a = await create_collection(client_a, session_a, name="Acme Files")
    collection_b = await create_collection(client_b, session_b, name="Globex Files")
    doc_a = await upload(
        client_a, session_a, collection_id=collection_a["id"],
        filename="a.txt", content=b"Acme secret merger documents for the timeline.",
    )
    doc_b = await upload(
        client_b, session_b, collection_id=collection_b["id"],
        filename="b.txt", content=b"Acme secret merger documents for the timeline.",
    )

    results_a = await search_direct(
        app, tenant_id=tenant_of(session_a), query="secret merger documents"
    )
    results_b = await search_direct(
        app, tenant_id=tenant_of(session_b), query="secret merger documents"
    )

    assert {chunk.document_id for chunk in results_a} == {doc_a["id"]}
    assert {chunk.document_id for chunk in results_b} == {doc_b["id"]}


async def test_malformed_ids_fail_closed(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    await upload(
        client, session, collection_id=collection["id"],
        filename="doc.txt", content=b"findable keywords live here today.",
    )
    tenant = tenant_of(session)

    assert await search_direct(app, tenant_id=tenant, query="findable keywords") != []
    assert await search_direct(app, tenant_id="not-a-uuid", query="findable keywords") == []
    assert await search_direct(
        app, tenant_id=str(uuid.uuid4()), query="findable keywords"
    ) == []
    assert await search_direct(
        app, tenant_id=tenant, query="findable keywords", collection_ids=["nope"]
    ) == []


async def test_collection_filter_restricts_candidates(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    col_one = await create_collection(client, session, name="One")
    col_two = await create_collection(client, session, name="Two")
    tenant = tenant_of(session)
    doc_one = await upload(
        client, session, collection_id=col_one["id"],
        filename="one.txt", content=b"Budget forecast numbers for next year.",
    )
    doc_two = await upload(
        client, session, collection_id=col_two["id"],
        filename="two.txt", content=b"Budget forecast numbers for next year.",
    )

    only_one = await search_direct(
        app, tenant_id=tenant, query="budget forecast",
        collection_ids=[col_one["id"]],
    )
    both = await search_direct(
        app, tenant_id=tenant, query="budget forecast",
        collection_ids=[col_one["id"], col_two["id"]],
    )
    unfiltered = await search_direct(app, tenant_id=tenant, query="budget forecast")

    assert {chunk.document_id for chunk in only_one} == {doc_one["id"]}
    assert {chunk.document_id for chunk in both} == {doc_one["id"], doc_two["id"]}
    assert {chunk.document_id for chunk in unfiltered} == {doc_one["id"], doc_two["id"]}


# ------------------------------------------------------------- read-only I/O
async def test_search_never_flushes_or_commits_pending_state(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    document = await upload(
        client, session, collection_id=collection["id"],
        filename="doc.txt", content=b"searchable material for the pending test.",
    )
    tenant = tenant_of(session)

    async with app.state.session_factory() as db:
        pending = DocumentChunk(
            tenant_id=uuid.UUID(tenant),
            document_id=uuid.UUID(document["id"]),
            collection_id=uuid.UUID(collection["id"]),
            chunk_id="pending-never-persisted",
            chunk_index=99,
            page=1,
            filename="pending.txt",
            text="pending row that search must not flush away",
        )
        db.add(pending)
        results = await SqlLexicalIndex(db).search(
            query="searchable material", tenant_id=tenant, top_k=5
        )
        # no flush and therefore no commit: the pending row is untouched
        assert pending in db.new
        assert results  # the SELECTs themselves did run
        await db.rollback()


async def test_search_without_fts_mirror_returns_empty_and_creates_nothing(
    app, actor_factory
):
    # registration only — nothing was ever ingested, so the FTS mirror table
    # does not exist yet and search must not create it
    _, session = await actor_factory(name="Bare", email="bare@example.com", org="Bare Co")

    results = await search_direct(
        app, tenant_id=tenant_of(session), query="anything at all"
    )
    assert results == []

    async with app.state.session_factory() as db:
        mirror = (
            await db.execute(
                text(
                    "SELECT count(*) FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'document_chunks_fts'"
                )
            )
        ).scalar_one()
    assert mirror == 0  # read-only search never ran DDL


# ------------------------------------------------------------ hostile input
@pytest.mark.parametrize(
    "hostile",
    ['"', "*", "(", '(" OR NOT', "NEAR(a b", "col:value", "a AND OR NOT", "^", "''"],
)
async def test_hostile_fts5_queries_never_raise(app, actor_factory, hostile):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    await upload(
        client, session, collection_id=collection["id"],
        filename="doc.txt", content=b"Ordinary indexed content for matching.",
    )
    results = await search_direct(
        app, tenant_id=tenant_of(session), query=hostile, top_k=10
    )
    assert isinstance(results, list)  # no exception, only sane candidates


async def test_hostile_queries_cannot_match_across_tenants(app, actor_factory):
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    collection_a = await create_collection(client_a, session_a, name="Files")
    collection_b = await create_collection(client_b, session_b, name="Files")
    await upload(
        client_a, session_a, collection_id=collection_a["id"],
        filename="a.txt", content=b"only for acme eyes really.",
    )
    doc_b = await upload(
        client_b, session_b, collection_id=collection_b["id"],
        filename="b.txt", content=b"only for globex eyes really.",
    )

    for hostile in ('" OR *', "NEAR(", "col:value OR"):
        results = await search_direct(
            app, tenant_id=tenant_of(session_a), query=hostile, top_k=10
        )
        assert doc_b["id"] not in {chunk.document_id for chunk in results}


# --------------------------------------------------------------------- bounds
async def test_result_count_never_exceeds_top_k_or_max_top_k(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    tenant = tenant_of(session)
    document = await upload(
        client, session, collection_id=collection["id"],
        filename="bulk.txt", content=b"placeholder.",
    )
    texts = [f"boundsterm variant number {index}" for index in range(60)]
    await seed_chunks(
        app, tenant_id=tenant, document_id=document["id"],
        collection_id=collection["id"], filename="bulk", texts=texts,
    )

    ten = await search_direct(app, tenant_id=tenant, query="boundsterm", top_k=10)
    over = await search_direct(app, tenant_id=tenant, query="boundsterm", top_k=55)
    way_over = await search_direct(
        app, tenant_id=tenant, query="boundsterm", top_k=9999
    )
    assert len(ten) == 10
    assert len(over) == MAX_TOP_K  # clamped at the hard retrieval cap
    assert len(way_over) == MAX_TOP_K
    assert await search_direct(app, tenant_id=tenant, query="boundsterm", top_k=0) == []
    assert await search_direct(app, tenant_id=tenant, query="boundsterm", top_k=-3) == []
    assert await search_direct(app, tenant_id=tenant, query="boundsterm", top_k="abc") == []
    assert await search_direct(app, tenant_id=tenant, query="   ", top_k=10) == []


# ------------------------------- retrieve_lexical: authorization enforcement
async def test_grant_and_revoke_change_lexical_results_without_reingestion(
    app, actor_factory
):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    member_client, member_session = await actor_factory(
        name="Mia Member", email="mia@acme.com",
        invited_by=(owner_client, owner_session), role="member",
    )
    member_id = member_session["user"]["id"]
    collection = await create_collection(owner_client, owner_session, name="HR")
    document = await upload(
        owner_client, owner_session, collection_id=collection["id"],
        filename="salary.txt",
        content=b"Salary band revision details for senior engineers in 2026.",
        classification="confidential",
    )

    before = await lexical_document_ids(
        app, session=member_session, query="salary band revision"
    )
    assert before == set()

    granted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": [member_id]},
        headers=auth(owner_session),
    )
    assert granted.status_code == 200, granted.text
    during = await lexical_document_ids(
        app, session=member_session, query="salary band revision"
    )
    assert during == {document["id"]}

    revoked = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": []},
        headers=auth(owner_session),
    )
    assert revoked.status_code == 200, revoked.text
    after = await lexical_document_ids(
        app, session=member_session, query="salary band revision"
    )
    assert after == set()  # revoked with NO re-ingestion

    regranted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": [member_id]},
        headers=auth(owner_session),
    )
    assert regranted.status_code == 200, regranted.text
    final = await lexical_document_ids(
        app, session=member_session, query="salary band revision"
    )
    assert final == {document["id"]}

    # the admin creator always sees their own document
    owner_view = await lexical_document_ids(
        app, session=owner_session, query="salary band revision"
    )
    assert owner_view == {document["id"]}


async def test_role_rules_apply_to_lexical_path(app, actor_factory):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    viewer_client, viewer_session = await actor_factory(
        name="Vic Viewer", email="vic@acme.com",
        invited_by=(owner_client, owner_session), role="viewer",
    )
    collection = await create_collection(owner_client, owner_session, name="Mixed")
    internal = await upload(
        owner_client, owner_session, collection_id=collection["id"],
        filename="handbook.txt",
        content=b"Onboarding handbook for all new employees this quarter.",
        classification="internal",
    )
    confidential = await upload(
        owner_client, owner_session, collection_id=collection["id"],
        filename="board.txt",
        content=b"Onboarding handbook for all new employees this quarter.",
        classification="confidential",
    )

    owner_ids = await lexical_document_ids(
        app, session=owner_session, query="onboarding handbook"
    )
    assert owner_ids == {internal["id"], confidential["id"]}

    viewer_ids = await lexical_document_ids(
        app, session=viewer_session, query="onboarding handbook"
    )
    assert viewer_ids == {internal["id"]}
    assert confidential["id"] not in viewer_ids


async def test_reranker_only_sees_authorized_lexical_chunks(app, actor_factory, monkeypatch):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    member_client, member_session = await actor_factory(
        name="Mia Member", email="mia@acme.com",
        invited_by=(owner_client, owner_session), role="member",
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
        owner_client, owner_session, collection_id=collection["id"],
        filename="secret.txt",
        content=b"salary band revision confidential engineering 2026",
        classification="confidential",
    )
    shared = await upload(
        owner_client, owner_session, collection_id=collection["id"],
        filename="shared.txt",
        content=b"salary band revision for everyone in the org today",
    )
    foreign = await upload(
        outsider_client, outsider_session, collection_id=outsider_collection["id"],
        filename="foreign.txt",
        content=b"salary band revision confidential engineering 2026",
    )

    recorder = RecordingReranker()
    async with app.state.session_factory() as db:
        results = await lexical_retriever(db, reranker=recorder).retrieve_lexical(
            query=query,
            tenant_id=tenant_of(member_session),
            user_id=member_session["user"]["id"],
            top_k=10,
        )

    assert recorder.calls, "the reranker must have been invoked"
    seen = {chunk.document_id for chunk in recorder.calls[0]}
    assert secret["id"] not in seen, "unauthorized chunk reached the reranker"
    assert foreign["id"] not in seen, "cross-tenant chunk reached the reranker"
    assert shared["id"] in seen, "the authorized chunk must reach the reranker"
    assert {chunk.document_id for chunk in results} == {shared["id"]}


async def test_retrieve_lexical_validates_input_and_membership(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")

    async with app.state.session_factory() as db:
        retriever = lexical_retriever(db)
        with pytest.raises(AppError) as empty:
            await retriever.retrieve_lexical(
                query="   ", tenant_id=tenant_of(session),
                user_id=session["user"]["id"],
            )
        assert empty.value.code == "VALIDATION_ERROR"

        with pytest.raises(AppError) as too_many:
            await retriever.retrieve_lexical(
                query="valid query", tenant_id=tenant_of(session),
                user_id=session["user"]["id"], top_k=MAX_TOP_K + 1,
            )
        assert too_many.value.code == "VALIDATION_ERROR"

        with pytest.raises(AuthorizationError) as outsider:
            await retriever.retrieve_lexical(
                query="anything at all",
                tenant_id=tenant_of(session),
                user_id=str(uuid.uuid4()),
            )
        assert outsider.value.code == "TENANT_ACCESS_DENIED"


async def test_retrieve_lexical_with_null_index_returns_nothing(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    await upload(
        client, session, collection_id=collection["id"],
        filename="doc.txt", content=b"findable keywords live here today.",
    )
    async with app.state.session_factory() as db:
        retriever = TenantScopedRetriever(
            db=db,
            embedder=HashingEmbeddingProvider(dimension=32),
            vector_store=None,  # type: ignore[arg-type]
            lexical_index=NullLexicalIndex(),
        )
        results = await retriever.retrieve_lexical(
            query="findable keywords",
            tenant_id=tenant_of(session),
            user_id=session["user"]["id"],
        )
    assert results == []


async def test_retrieve_lexical_failure_is_safe_503_without_reranking(
    app, actor_factory, monkeypatch
):
    async def exploding_search(self, **kwargs):
        raise RuntimeError("fts backend exploded with password=sk-LEX-LEAK")

    monkeypatch.setattr(SqlLexicalIndex, "search", exploding_search)
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    recorder = RecordingReranker()

    async with app.state.session_factory() as db:
        with pytest.raises(AppError) as excinfo:
            await lexical_retriever(db, reranker=recorder).retrieve_lexical(
                query="findable keywords",
                tenant_id=tenant_of(session),
                user_id=session["user"]["id"],
            )

    assert excinfo.value.code == "SERVICE_UNAVAILABLE"
    assert excinfo.value.status_code == 503
    assert "sk-lex-leak" not in excinfo.value.message.lower()
    assert recorder.calls == [], "no partial/unauthorized candidates may reach the reranker"


# ------------------------------------------- PostgreSQL branch (construction)
def test_postgres_statement_shape_matches_migration_expression():
    sql = postgres_search_statement(0)
    # byte-identical to migration 0002's GIN index expression (twice: select + match)
    assert sql.count("to_tsvector('simple', text)") == 2
    assert "websearch_to_tsquery('simple', :query)" in sql
    assert "ts_rank_cd(" in sql
    assert "WHERE tenant_id = :tenant_id" in sql
    assert "ORDER BY score DESC, chunk_id ASC" in sql
    assert "LIMIT :fetch" in sql
    assert ":c" not in sql  # no collection clause without a filter


def test_postgres_statement_composes_only_placeholder_names():
    sql = postgres_search_statement(3)
    assert "AND collection_id IN (:c0, :c1, :c2)" in sql
    assert "IN (:c0, :c1, :c2)" in sql
    # values never appear in SQL text — only placeholder tokens
    assert "00000000" not in sql
    assert "SELECT " in sql and "INSERT" not in sql and "UPDATE" not in sql


class _NoAutoflush:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    """Captures (sql, params) of every execute — PG can be asserted without a server."""

    sync_session = type("S", (), {"no_autoflush": _NoAutoflush()})()

    def __init__(self, rows=None):
        self.calls: list[tuple[str, dict]] = []
        self.rows = list(rows or [])

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return _FakeResult(self.rows)


async def test_postgres_branch_binds_values_never_sql_text(monkeypatch):
    tenant = str(uuid.uuid4())
    col_a, col_b = str(uuid.uuid4()), str(uuid.uuid4())
    fake = _FakeDb()
    monkeypatch.setattr(
        SqlLexicalIndex, "_dialect", property(lambda self: "postgresql")
    )
    index = SqlLexicalIndex(fake)

    results = await index.search(
        query='alpha "beta" (gamma) OR',
        tenant_id=tenant,
        collection_ids=[col_a, col_b],
        top_k=7,
    )

    assert results == []  # fake returns no rows; the assertion is the binding
    assert len(fake.calls) == 1
    sql, params = fake.calls[0]
    assert "websearch_to_tsquery" in sql
    assert "AND collection_id IN (:c0, :c1)" in sql
    assert params == {
        "query": "alpha beta gamma",  # sanitised: quotes/parens/operator gone
        "tenant_id": tenant,
        "fetch": 7,
        "c0": col_a,
        "c1": col_b,
    }
    # no bound value leaks into the SQL text itself
    assert tenant not in sql and col_a not in sql and col_b not in sql


async def test_postgres_branch_maps_rows_and_preserves_rank_order(monkeypatch):
    """No live server: validate the PostgreSQL branch's result mapping offline."""
    tenant = str(uuid.uuid4())
    collection = str(uuid.uuid4())
    document = str(uuid.uuid4())
    rows = [
        SimpleNamespace(
            chunk_id="pg-chunk-1",
            document_id=document,
            collection_id=collection,
            page=2,
            filename="handbook.txt",
            text="first ranked passage about leave policy",
            chunk_index=4,
            score=0.75,
        ),
        SimpleNamespace(
            chunk_id="pg-chunk-2",
            document_id=document,
            collection_id=collection,
            page=1,
            filename="handbook.txt",
            text="second ranked passage about leave policy",
            chunk_index=1,
            score=0.25,
        ),
    ]
    fake = _FakeDb(rows)
    monkeypatch.setattr(
        SqlLexicalIndex, "_dialect", property(lambda self: "postgresql")
    )

    results = await SqlLexicalIndex(fake).search(
        query="leave policy",
        tenant_id=tenant,
        collection_ids=[collection],
        top_k=2,
    )

    assert [chunk.chunk_id for chunk in results] == ["pg-chunk-1", "pg-chunk-2"]
    assert [chunk.score for chunk in results] == [0.75, 0.25]
    first = results[0]
    assert first.document_id == document
    assert first.collection_id == collection
    assert first.page_number == 2
    assert first.filename == "handbook.txt"
    assert first.quote == "first ranked passage about leave policy"
    assert first.metadata == {"chunk_index": 4}
    sql, params = fake.calls[0]
    assert "websearch_to_tsquery" in sql
    assert params["query"] == "leave policy"
    assert params["tenant_id"] == tenant
    assert params["fetch"] == 2
    assert params["c0"] == collection


async def test_unknown_engine_fails_closed(app, actor_factory, monkeypatch):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Docs")
    await upload(
        client, session, collection_id=collection["id"],
        filename="doc.txt", content=b"findable keywords live here today.",
    )
    monkeypatch.setattr(SqlLexicalIndex, "_dialect", property(lambda self: "oracle"))
    results = await search_direct(
        app, tenant_id=tenant_of(session), query="findable keywords"
    )
    assert results == []


# -------------------------------------------------- vector-mode regression (M)
async def test_vector_retrieve_never_calls_lexical_search(app, actor_factory, monkeypatch):
    calls: list[dict] = []
    original = SqlLexicalIndex.search

    async def spy(self, **kwargs):
        calls.append(kwargs)
        return await original(self, **kwargs)

    monkeypatch.setattr(SqlLexicalIndex, "search", spy)

    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Policies")
    document = await upload(
        client, session, collection_id=collection["id"],
        filename="remote.txt",
        content=b"Remote work policy allows flextime on Fridays.",
    )

    response = await retrieve(client, session, query="remote work policy flextime")
    assert response.status_code == 200, response.text
    hits = response.json()
    assert hits, "vector retrieval must still work unchanged"
    assert document_ids(response) == {document["id"]}

    assert calls == [], "the vector-only retrieve() path must never run lexical search"
    assert app.state.settings.retrieval_mode == "vector"
