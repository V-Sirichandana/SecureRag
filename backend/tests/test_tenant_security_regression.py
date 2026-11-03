"""Focused multi-tenant security regression tests (audit follow-up).

The broader suites already pin cross-tenant isolation at the document,
retrieval and chat level; this module adds the focused regressions that close
the remaining coverage gaps:

* a foreign ``X-Tenant-Id`` identity hint must never widen a caller's scope on
  the tenant-scoped document, collection, retrieval or chat boundaries - the
  authenticated membership stays the only tenant authority;
* an AI answer generated for one tenant must never be based on, or cite,
  chunks of another tenant's documents (context, citations and answer).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from tests.conftest import auth, create_collection
from tests.test_chat_generation import install_fake_provider
from tests.test_retrieval import upload

TEST_JWT = "test-secret-key-not-for-production"
FAKE_KEY = "sk-test-key-not-real"


@pytest_asyncio.fixture
async def app(tmp_path):
    application = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            jwt_secret_key=TEST_JWT,
            database_url="sqlite+aiosqlite:///:memory:",
            qdrant_url=":memory:",
            storage_dir=str(tmp_path / "uploads"),
            llm_provider="openai",
            llm_api_key=FAKE_KEY,
            llm_model="test-model",
        )
    )
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


@pytest.fixture
async def tenant_a(actor_factory):
    return await actor_factory(name="Alice Owner", email="alice@example.com", org="Acme Corp")


@pytest.fixture
async def tenant_b(actor_factory):
    return await actor_factory(name="Bob Owner", email="bob@example.org", org="Globex Inc")


# ------------------------------------------- 1. identity hint boundaries
@pytest.mark.parametrize(
    "path",
    [
        "/documents",
        "/documents/00000000-0000-0000-0000-000000000000",
        "/collections",
        "/collections/00000000-0000-0000-0000-000000000000",
        "/chat/conversations",
    ],
)
async def test_foreign_tenant_hint_is_rejected_on_tenant_scoped_boundaries(
    tenant_a, tenant_b, path
):
    client_a, session_a = tenant_a
    _client_b, session_b = tenant_b

    response = await client_a.get(
        path, headers={**auth(session_a), "X-Tenant-Id": session_b["user"]["organizationId"]}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


async def test_foreign_tenant_hint_is_rejected_on_retrieval_boundary(tenant_a, tenant_b):
    client_a, session_a = tenant_a
    _client_b, session_b = tenant_b

    response = await client_a.post(
        "/search/retrieve",
        json={"query": "anything"},
        headers={**auth(session_a), "X-Tenant-Id": session_b["user"]["organizationId"]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


async def test_foreign_tenant_hint_is_rejected_on_chat_message_boundary(tenant_a, tenant_b):
    client_b, session_b = tenant_b
    conversation = await client_b.post(
        "/chat/conversations", json={"title": "Bob private chat"}, headers=auth(session_b)
    )
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]

    client_a, session_a = tenant_a
    response = await client_a.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "read tenant b notes"},
        headers={**auth(session_a), "X-Tenant-Id": session_b["user"]["organizationId"]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


# ------------------------------------------- 2. chat answer + citation isolation
async def test_tenant_b_answer_and_citations_never_reference_tenant_a_documents(
    app, actor_factory, monkeypatch
):
    calls = install_fake_provider(
        app, monkeypatch, answer="Tenant B answer grounded on its own document. [1]"
    )

    client_a, session_a = await actor_factory(
        name="Alice Owner", email="alice@example.com", org="Acme Corp"
    )
    client_b, session_b = await actor_factory(
        name="Bob Owner", email="bob@example.org", org="Globex Inc"
    )

    collection_a = await create_collection(client_a, session_a, name="Acme Files")
    document_a = await upload(
        client_a,
        session_a,
        collection_id=collection_a["id"],
        filename="acme-secret.txt",
        content=b"Acme secret merger documents describe the acquisition timeline.",
        classification="confidential",
    )

    collection_b = await create_collection(client_b, session_b, name="Globex Files")
    document_b = await upload(
        client_b,
        session_b,
        collection_id=collection_b["id"],
        filename="globex-notes.txt",
        content=b"Globex notes describe the shipping logistics routine.",
        classification="internal",
    )

    conversation_b = await client_b.post(
        "/chat/conversations",
        json={"title": "Bob private chat", "collectionId": collection_b["id"]},
        headers=auth(session_b),
    )
    assert conversation_b.status_code == 201
    conversation_id = conversation_b.json()["id"]

    response = await client_b.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "What does the notes say about shipping?"},
        headers=auth(session_b),
    )
    assert response.status_code == 201, response.text

    # the provider only ever saw tenant B's authorized retrieval context
    assert len(calls) == 1
    context = calls[0]["context"]
    context_ids = {chunk.document_id for chunk in context}
    assert context_ids == {document_b["id"]}, context
    assert all(chunk.document_id != document_a["id"] for chunk in context)
    assert all("Acme secret" not in chunk.text for chunk in context)

    # the generated answer is grounded in that context and cites it
    assert response.json()["citations"], "the answer must carry citations from context"
    citations = response.json()["citations"]
    assert {citation["documentId"] for citation in citations} == {document_b["id"]}
    for citation in citations:
        assert citation["documentId"] != document_a["id"]
        assert citation["chunkId"] in {chunk.chunk_id for chunk in context}
