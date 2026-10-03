"""Secure retrieval: tenant isolation + CURRENT permission enforcement.

The database is authoritative: revoking or granting document access must
change search results immediately, with NO re-ingestion in between.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.config import Settings
from app.core.exceptions import AppError, AuthorizationError
from app.db.database import create_all, drop_all
from app.main import create_app
from app.services.ingestion.embeddings import HashingEmbeddingProvider
from app.services.rag.base import RetrievedChunk
from app.services.rag.retriever import TenantScopedRetriever
from tests.conftest import auth, create_collection, make_client, register

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


@pytest_asyncio.fixture
async def app_no_vector_store(tmp_path):
    application = create_app(
        Settings(
            app_env="test",
            jwt_secret_key=TEST_JWT,
            database_url="sqlite+aiosqlite:///:memory:",
            qdrant_url="",
            storage_dir=str(tmp_path / "nvs"),
        )
    )
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


async def upload(
    client: AsyncClient,
    session: dict,
    *,
    collection_id: str,
    filename: str,
    content: bytes,
    classification: str = "internal",
) -> dict:
    response = await client.post(
        "/documents/upload",
        files={"file": (filename, content, "text/plain")},
        data={"collection_id": collection_id, "classification": classification},
        headers=auth(session),
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ready", response.text
    return response.json()


async def retrieve(
    client: AsyncClient, session: dict, *, query: str, top_k: int = 10, **extra
):
    return await client.post(
        "/search/retrieve",
        json={"query": query, "top_k": top_k, **extra},
        headers=auth(session),
    )


def document_ids(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {hit["documentId"] for hit in response.json()}


# ------------------------------------------------------------------ happy path
async def test_same_tenant_search_returns_authorized_chunks(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Policies")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="remote.txt",
        content=b"Our remote work policy allows flextime on Fridays and remote weeks.",
    )

    response = await retrieve(client, session, query="remote work policy flextime")
    assert response.status_code == 200, response.text
    hits = response.json()
    assert hits, "the indexed document must be retrievable"
    assert document_ids(response) == {document["id"]}

    hit = hits[0]
    assert hit["content"]
    assert hit["chunkId"]
    assert hit["documentId"] == document["id"]
    assert isinstance(hit["score"], float)
    assert hit["page"] >= 1
    assert hit["filename"] == "remote.txt"
    assert hit["metadata"]["tenant_id"] == session["user"]["organizationId"]
    assert hit["metadata"]["document_name"] == "remote.txt"


async def test_no_results_returns_clean_empty_list(app, actor_factory):
    client, session = await actor_factory(name="Zoe", email="zoe@example.com", org="Empty Co")
    response = await retrieve(client, session, query="anything at all")
    assert response.status_code == 200, response.text
    assert response.json() == []


# ---------------------------------------------------------------- cross-tenant
async def test_cross_tenant_search_never_returns_foreign_chunks(app, actor_factory):
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
        filename="acme.txt",
        content=b"Acme secret merger documents describe the acquisition timeline.",
    )
    doc_b = await upload(
        client_b,
        session_b,
        collection_id=collection_b["id"],
        filename="globex.txt",
        content=b"Acme secret merger documents describe the acquisition timeline.",
    )

    response_a = await retrieve(client_a, session_a, query="secret merger documents")
    assert document_ids(response_a) == {doc_a["id"]}
    assert doc_b["id"] not in document_ids(response_a)

    response_b = await retrieve(client_b, session_b, query="secret merger documents")
    assert document_ids(response_b) == {doc_b["id"]}
    assert doc_a["id"] not in document_ids(response_b)


async def test_foreign_tenant_hint_in_body_is_ignored(app, actor_factory):
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
        content=b"Acme internal checklist for the quarter.",
    )
    doc_b = await upload(
        client_b,
        session_b,
        collection_id=collection_b["id"],
        filename="b.txt",
        content=b"Acme internal checklist for the quarter.",
    )
    tenant_b = session_b["user"]["organizationId"]

    response = await retrieve(
        client_a,
        session_a,
        query="internal checklist",
        tenant_id=tenant_b,  # ignored: not part of the schema
        tenantId=tenant_b,  # ignored as well
        allowed_document_ids=[doc_b["id"]],  # ignored: authorization is server-side
    )
    assert response.status_code == 200, response.text
    ids = document_ids(response)
    assert ids == {doc_a["id"]}
    assert doc_b["id"] not in ids


# ------------------------------------------- current permission enforcement (§12)
async def test_permission_grant_and_revoke_without_reingestion(app, actor_factory):
    """MANDATORY: authorization changes take effect with NO re-index."""
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

    # 1-2. upload/index a CONFIDENTIAL document (no org-wide grant)
    document = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="salary.txt",
        content=b"Salary band revision details for senior engineers in 2026.",
        classification="confidential",
    )

    # 3-4. member has no access yet → search must not surface it
    before = await retrieve(member_client, member_session, query="salary band revision")
    assert document_ids(before) == set()

    # 5. grant the member current access (no re-ingestion)
    granted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": [member_id]},
        headers=auth(owner_session),
    )
    assert granted.status_code == 200, granted.text

    # 6-7. search now returns the document
    during = await retrieve(member_client, member_session, query="salary band revision")
    assert document_ids(during) == {document["id"]}

    # 8. revoke again (no re-ingestion, no payload change)
    revoked = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": []},
        headers=auth(owner_session),
    )
    assert revoked.status_code == 200, revoked.text

    # 9. search must NOT return it anymore — Qdrant still holds the vectors
    after = await retrieve(member_client, member_session, query="salary band revision")
    assert document_ids(after) == set()

    # 10. grant again → appears again, still without re-ingestion
    regranted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": [member_id]},
        headers=auth(owner_session),
    )
    assert regranted.status_code == 200, regranted.text
    final = await retrieve(member_client, member_session, query="salary band revision")
    assert document_ids(final) == {document["id"]}

    # control: the admin creator always sees their own confidential document
    owner_view = await retrieve(owner_client, owner_session, query="salary band revision")
    assert document_ids(owner_view) == {document["id"]}


async def test_rbac_role_rules_are_respected(app, actor_factory):
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

    # admin+ sees every tenant document (existing _can_view rule)
    owner_ids = document_ids(
        await retrieve(owner_client, owner_session, query="onboarding handbook")
    )
    assert owner_ids == {internal["id"], confidential["id"]}

    # viewer may search but only receives org-wide visible documents
    viewer_response = await retrieve(viewer_client, viewer_session, query="onboarding handbook")
    assert viewer_response.status_code == 200, viewer_response.text
    viewer_ids = document_ids(viewer_response)
    assert viewer_ids == {internal["id"]}
    assert confidential["id"] not in viewer_ids


# ------------------------------------------------------------------ validation
async def test_empty_and_whitespace_queries_rejected(app, actor_factory):
    client, session = await actor_factory(name="Val", email="val@example.com", org="Validate")

    empty = await retrieve(client, session, query="")
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "VALIDATION_ERROR"

    # the schema strips whitespace, so blanks fail at validation too
    blank = await retrieve(client, session, query="   ")
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "VALIDATION_ERROR"

    # defense in depth: the retriever itself refuses blank input
    with pytest.raises(AppError) as excinfo:
        TenantScopedRetriever._validate("   ", 10)
    assert excinfo.value.code == "VALIDATION_ERROR"
    assert "empty" in excinfo.value.message.lower()


async def test_query_too_long_rejected(app, actor_factory):
    client, session = await actor_factory(name="Long", email="long@example.com", org="Validate")
    response = await retrieve(client, session, query="a" * 1001)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("top_k", [0, -1, 51, 1000])
async def test_invalid_top_k_rejected(app, actor_factory, top_k):
    client, session = await actor_factory(
        name=f"TopK{top_k}", email=f"topk{top_k}@example.com", org="Validate"
    )
    response = await retrieve(client, session, query="valid query", top_k=top_k)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ------------------------------------------------------------ failure handling
async def test_vector_store_failure_returns_safe_error(app, actor_factory, monkeypatch):
    client, session = await actor_factory(name="Fail", email="fail@example.com", org="Ops")

    class ExplodingStore:
        async def search(self, **kwargs):
            raise RuntimeError("qdrant at 127.0.0.1:6333 exploded with api_key=sk-LEAK")

        async def upsert_chunks(self, **kwargs):  # pragma: no cover - unused
            raise NotImplementedError

        async def delete_document(self, **kwargs):  # pragma: no cover - unused
            raise NotImplementedError

    monkeypatch.setattr(app.state, "vector_store", ExplodingStore())

    response = await retrieve(client, session, query="anything")
    assert response.status_code == 503
    body = response.text.lower()
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "sk-leak" not in body
    assert "127.0.0.1" not in body
    assert "qdrant" not in body
    assert "traceback" not in body


async def test_embedding_failure_returns_safe_error(app, actor_factory, monkeypatch):
    client, session = await actor_factory(name="Embed", email="embed@example.com", org="Ops")

    class ExplodingEmbedder:
        async def embed_query(self, text):
            raise RuntimeError("embedding backend said api_key=sk-EMBED-LEAK")

    monkeypatch.setattr(
        "app.services.rag.get_embedding_service", lambda settings: ExplodingEmbedder()
    )

    response = await retrieve(client, session, query="anything")
    assert response.status_code == 503
    body = response.text.lower()
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "sk-embed-leak" not in body
    assert "traceback" not in body


async def test_unconfigured_vector_store_returns_501(app_no_vector_store):
    # NOTE: cannot use actor_factory here — its `app` dependency would resolve
    # to the module-level working app instead of app_no_vector_store.
    async with make_client(app_no_vector_store) as client:
        session = await register(
            client, name="NoQ", email="noq@example.com", org="No Vector"
        )
        response = await retrieve(client, session, query="anything")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "SERVICE_NOT_CONFIGURED"


async def test_non_member_cannot_retrieve(app):
    async with app.state.session_factory() as db:
        retriever = TenantScopedRetriever(
            db=db,
            embedder=HashingEmbeddingProvider(dimension=32),
            vector_store=None,  # type: ignore[arg-type] - never reached
        )
        with pytest.raises(AuthorizationError) as excinfo:
            await retriever.retrieve(
                query="anything",
                tenant_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
            )
    assert excinfo.value.code == "TENANT_ACCESS_DENIED"


# ----------------------------------------------- bounded candidate expansion (§7)
class ScriptedStore:
    """Returns scripted candidate rounds; counts its calls."""

    def __init__(self, rounds: list[list[RetrievedChunk]]) -> None:
        self.rounds = rounds
        self.calls = 0

    async def search(
        self,
        *,
        vector,
        tenant_id,
        collection_id=None,
        document_ids=None,
        top_k=8,
        extra_filter=None,
    ) -> list[RetrievedChunk]:
        round_index = min(self.calls, len(self.rounds) - 1)
        self.calls += 1
        return self.rounds[round_index][:top_k]


def _candidates(document_id: str, count: int, *, prefix: str) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            text=f"{prefix} text {index}",
            score=0.9 - index * 0.01,
            document_id=document_id,
            chunk_id=str(uuid.uuid4()),
        )
        for index in range(count)
    ]


async def test_candidate_expansion_filters_unauthorized_results(app, actor_factory):
    """Top-ranked but unauthorized chunks are dropped; expansion is bounded."""
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    member_client, member_session = await actor_factory(
        name="Mia Member",
        email="mia@acme.com",
        invited_by=(owner_client, owner_session),
        role="member",
    )
    collection = await create_collection(owner_client, owner_session, name="Mixed")

    secret = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="secret.txt",
        content=b"Top secret merger content that a member must never retrieve.",
        classification="confidential",
    )
    shared = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="shared.txt",
        content=b"Shared onboarding content visible to the whole tenant.",
    )

    # round 1: 12 candidates (the initial fetch), only ONE authorized
    # round 2: 24 candidates, three authorized → enough for top_k=3
    script = ScriptedStore(
        [
            _candidates(secret["id"], 11, prefix="secret")  # highest ranked
            + _candidates(shared["id"], 1, prefix="shared"),
            _candidates(secret["id"], 21, prefix="secret")
            + _candidates(shared["id"], 3, prefix="shared"),
        ]
    )

    async with app.state.session_factory() as db:
        retriever = TenantScopedRetriever(
            db=db,
            embedder=HashingEmbeddingProvider(dimension=384),
            vector_store=script,
        )
        results = await retriever.retrieve(
            query="merger content",
            tenant_id=tenant_of(owner_session),
            user_id=member_session["user"]["id"],
            top_k=3,
        )

    assert len(results) == 3
    assert {result.document_id for result in results} == {shared["id"]}
    assert all(result.document_id != secret["id"] for result in results)
    assert script.calls == 2  # bounded expansion, not an unbounded loop


def tenant_of(session: dict) -> str:
    return session["user"]["organizationId"]
