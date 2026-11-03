"""M6.1 — end-to-end acceptance: upload → index → retrieve → generate → cite.

Unlike the unit-level suites, every test here drives the REAL pipeline over
HTTP: multipart file upload, extraction, chunking, hashing embeddings, the
embedded Qdrant vector store, hybrid (vector + FTS5) retrieval, and the chat
generation path with server-built citations, persistence and QUERY audit.

The only substituted component is the answer provider, registered at the
provider-registry boundary because no real LLM credentials exist in this
environment — the answer TEXT is scripted, but the context handed to the
provider, the citations the backend derives from that context, and every
persistence/audit step are real.

Synthetic fixture content only; no user documents are touched.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import AsyncClient

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from app.services.rag import _LLM_PROVIDERS
from app.services.rag.base import GenerationResult
from tests.conftest import auth, create_collection

TEST_JWT = "test-secret-key-not-for-production"

AURORA_TEXT = (
    b"Project Aurora uses the internal reference code SR-4821. "
    b"Its designated test location is Hyderabad. "
    b"The review month is October 2026."
)
DECOY_TEXT = (
    b"The quarterly facilities maintenance schedule covers the Bengaluru office. "
    b"The cafeteria is closed on weekends and public holidays."
)


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
            retrieval_mode="hybrid",
            # deterministic: never inherit answer-provider config from .env/env
            llm_provider="",
            llm_api_key="",
            llm_model="",
        )
    )
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


# --------------------------------------------------------------------- helpers
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
    document = response.json()
    assert document["status"] == "ready", response.text
    return document


async def retrieve(client, session, query: str, *, top_k: int = 10) -> list[dict]:
    response = await client.post(
        "/search/retrieve",
        json={"query": query, "top_k": top_k},
        headers=auth(session),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def create_conversation(client, session, **payload) -> dict:
    response = await client.post(
        "/chat/conversations", json={"title": "New conversation", **payload}, headers=auth(session)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def ask(client, session, conversation_id: str, question: str):
    return await client.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"role": "user", "content": question},
        headers=auth(session),
    )


async def messages_of(client, session, conversation_id: str) -> list[dict]:
    response = await client.get(
        f"/chat/conversations/{conversation_id}", headers=auth(session)
    )
    assert response.status_code == 200, response.text
    return response.json()["messages"]


async def query_audits(client, session) -> list[dict]:
    response = await client.get("/audit", params={"action": "QUERY"}, headers=auth(session))
    assert response.status_code == 200, response.text
    return response.json()


def install_fake_provider(
    app,
    monkeypatch,
    *,
    answer: str,
    calls: list,
    provider_citations: list | None = None,
) -> None:
    """Register a scripted provider at the registry boundary the factory
    resolves — everything except the answer text runs production code."""
    settings = app.state.settings
    settings.llm_provider = "openai"
    settings.llm_model = "test-model"
    settings.llm_api_key = "sk-test-key-not-real"

    class FakeProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def generate(self, *, system, prompt, context, max_tokens=1024):
            calls.append({"system": system, "prompt": prompt, "context": list(context)})
            return GenerationResult(
                content=answer,
                citations=list(provider_citations or []),
                model="fake-model",
                latency_ms=5,
                token_count=4,
            )

    monkeypatch.setitem(_LLM_PROVIDERS, "openai", FakeProvider)


# -------------------------------------------------- Phase 2: upload → index
async def test_upload_fixture_is_indexed_end_to_end(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Aurora Project")

    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="aurora-notes.txt",
        content=AURORA_TEXT,
    )

    assert document["fileType"] == "txt"
    assert document["chunkCount"] >= 1
    assert document["pageCount"] >= 1
    assert document["collectionId"] == collection["id"]
    assert document["sizeBytes"] == len(AURORA_TEXT)


# ------------------------------------------------ Phase 3: retrieval quality
async def test_retrieval_finds_distinctive_facts(app, actor_factory):
    """Exact/overlap questions rank the fixture first under hybrid retrieval."""
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Aurora Project")
    fixture = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="aurora-notes.txt",
        content=AURORA_TEXT,
    )
    decoy = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="facilities.txt",
        content=DECOY_TEXT,
    )

    # 1. distinctive reference code — shared tokens, must rank first
    hits = await retrieve(client, session, "internal reference code SR-4821")
    assert hits, "expected at least one hit for the reference-code query"
    top = hits[0]
    assert top["documentId"] == fixture["id"], hits
    assert "SR-4821" in top["content"]
    assert top["collectionId"] == collection["id"]
    assert top["filename"] == "aurora-notes.txt"
    assert top["page"] >= 1

    # 2. designated test location — fixture tokens overlap the question
    hits = await retrieve(client, session, "designated test location")
    assert hits[0]["documentId"] == fixture["id"], hits
    assert "Hyderabad" in hits[0]["content"]

    # 3. review month
    hits = await retrieve(client, session, "review month October 2026")
    assert hits[0]["documentId"] == fixture["id"], hits
    assert "October 2026" in hits[0]["content"]

    # 4. semantic-style question WITHOUT token overlap: with hashing embeddings
    #    (not a semantic model) we only claim RECALL — the fixture must be in
    #    the bounded result set — never a rank guarantee. See the M6.1 report.
    hits = await retrieve(client, session, "Which Indian city hosts the trials?")
    document_ids = [hit["documentId"] for hit in hits]
    assert fixture["id"] in document_ids
    assert decoy["id"] in document_ids  # both docs fit within top_k


async def test_retrieval_limits_are_enforced(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Aurora Project")
    await upload(
        client, session, collection_id=collection["id"], filename="a.txt", content=AURORA_TEXT
    )

    too_small = await client.post(
        "/search/retrieve",
        json={"query": "SR-4821", "top_k": 0},
        headers=auth(session),
    )
    assert too_small.status_code == 422, too_small.text

    too_large = await client.post(
        "/search/retrieve",
        json={"query": "SR-4821", "top_k": 51},
        headers=auth(session),
    )
    assert too_large.status_code == 422, too_large.text

    bounded = await retrieve(client, session, "SR-4821", top_k=1)
    assert len(bounded) <= 1


# --------------------------------- Phase 4+5: generation, citations, audit
async def test_chat_answer_is_grounded_and_cited_from_uploaded_document(
    app, actor_factory, monkeypatch
):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Aurora Project")
    fixture = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="aurora-notes.txt",
        content=AURORA_TEXT,
    )
    conversation = await create_conversation(client, session)

    calls: list = []
    install_fake_provider(
        app,
        monkeypatch,
        answer="Project Aurora's reference code is SR-4821 and its test location is Hyderabad [1].",
        calls=calls,
    )

    response = await ask(
        client, session, conversation["id"], "What is Project Aurora's reference code?"
    )
    assert response.status_code == 201, response.text
    assistant = response.json()
    assert assistant["role"] == "assistant"
    assert "SR-4821" in assistant["content"]
    assert assistant["model"] == "fake-model"

    # the provider received the REALLY-RETRIEVED fixture chunk as context
    assert len(calls) == 1
    context_texts = [chunk.text for chunk in calls[0]["context"]]
    assert any("SR-4821" in text for text in context_texts), context_texts

    # citations were rebuilt server-side from that context
    citations = assistant["citations"]
    assert len(citations) == 1
    citation = citations[0]
    assert citation["documentId"] == fixture["id"]
    assert citation["documentName"] == "aurora-notes.txt"
    assert citation["collectionId"] == collection["id"]
    assert citation["collectionName"] == "Aurora Project"
    assert citation["pageNumber"] >= 1
    assert "SR-4821" in citation["quote"]

    # both messages persisted, ordered question-first, plus the QUERY audit
    messages = await messages_of(client, session, conversation["id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]
    audits = await query_audits(client, session)
    assert audits, "expected a QUERY audit event for the generated answer"


async def test_provider_cannot_inject_citation_metadata(app, actor_factory, monkeypatch):
    """A provider returning fabricated citations with a marker-free answer
    contributes nothing — citations come only from retrieved chunks."""
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Aurora Project")
    await upload(
        client, session, collection_id=collection["id"], filename="aurora-notes.txt",
        content=AURORA_TEXT,
    )
    conversation = await create_conversation(client, session)

    calls: list = []
    install_fake_provider(
        app,
        monkeypatch,
        answer="I could not find that in the indexed documents.",
        calls=calls,
        provider_citations=[
            {
                "index": 7,
                "documentId": "forged-doc-id",
                "documentName": "forged.pdf",
                "collectionId": "forged-collection",
                "collectionName": "Forged Collection",
                "pageNumber": 99,
                "quote": "forged quote",
            }
        ],
    )

    response = await ask(client, session, conversation["id"], "Reference code SR-4821?")
    assert response.status_code == 201, response.text
    assert response.json()["citations"] == []


# --------------------------------------------- Phase 6: tenant isolation e2e
async def test_foreign_org_cannot_retrieve_or_cite_the_fixture(app, actor_factory, monkeypatch):
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    collection_a = await create_collection(client_a, session_a, name="Aurora Project")
    fixture_a = await upload(
        client_a,
        session_a,
        collection_id=collection_a["id"],
        filename="aurora-secret.txt",
        content=AURORA_TEXT,
        classification="confidential",
    )

    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    collection_b = await create_collection(client_b, session_b, name="Globex Docs")
    await upload(
        client_b,
        session_b,
        collection_id=collection_b["id"],
        filename="globex-notes.txt",
        content=DECOY_TEXT,
    )

    # 1. Org B's retrieval never surfaces Org A's document
    hits = await retrieve(client_b, session_b, "internal reference code SR-4821 Hyderabad")
    assert fixture_a["id"] not in [hit["documentId"] for hit in hits], hits

    # 2. Org A still retrieves its own document
    hits_a = await retrieve(client_a, session_a, "internal reference code SR-4821")
    assert hits_a and hits_a[0]["documentId"] == fixture_a["id"], hits_a

    # 3. Org B asking about SR-4821 sends ZERO Org-A content to the provider
    conversation_b = await create_conversation(client_b, session_b)
    calls: list = []
    install_fake_provider(
        app,
        monkeypatch,
        answer="The indexed documents do not contain that reference [1].",
        calls=calls,
    )
    response = await ask(client_b, session_b, conversation_b["id"], "What is SR-4821?")
    assert response.status_code == 201, response.text

    assert len(calls) == 1
    for chunk in calls[0]["context"]:
        assert "SR-4821" not in chunk.text
        assert str(chunk.document_id) != fixture_a["id"]

    # 4. Org B's citations can only reference Org B's own documents
    for citation in response.json()["citations"] or []:
        assert citation["documentId"] != fixture_a["id"]
        assert citation["documentName"] != "aurora-secret.txt"


async def test_source_preview_serves_real_text_and_stays_tenant_scoped(
    app, actor_factory
):
    """The citation preview endpoint returns the text actually ingested, and
    only for the tenant that owns the document."""
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    collection_a = await create_collection(client_a, session_a, name="Aurora Project")
    fixture_a = await upload(
        client_a,
        session_a,
        collection_id=collection_a["id"],
        filename="aurora-secret.txt",
        content=AURORA_TEXT,
        classification="confidential",
    )

    response = await client_a.get(
        f"/documents/{fixture_a['id']}/pages", headers=auth(session_a)
    )
    assert response.status_code == 200, response.text
    pages = response.json()
    assert pages and pages[0]["pageNumber"] == 1
    paragraphs = [paragraph for page in pages for paragraph in page["paragraphs"]]
    assert paragraphs, "expected extracted text paragraphs for the preview"
    combined = " ".join(paragraph["text"] for paragraph in paragraphs)
    assert "SR-4821" in combined and "Hyderabad" in combined

    # a foreign org cannot read the preview either
    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    foreign = await client_b.get(
        f"/documents/{fixture_a['id']}/pages", headers=auth(session_b)
    )
    assert foreign.status_code == 404, foreign.text


async def test_conversation_collection_scope_is_enforced_end_to_end(
    app, actor_factory, monkeypatch
):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    hr = await create_collection(client, session, name="HR")
    finance = await create_collection(client, session, name="Finance")
    await upload(
        client, session, collection_id=hr["id"], filename="leave-policy.txt",
        content=b"Employees receive twenty days of annual leave per calendar year.",
    )
    await upload(
        client, session, collection_id=finance["id"], filename="runway.txt",
        content=b"The company runway is eighteen months at the current burn rate.",
    )

    conversation = await create_conversation(client, session, collection_id=hr["id"])
    calls: list = []
    install_fake_provider(
        app, monkeypatch, answer="Employees receive twenty days of annual leave [1].", calls=calls
    )

    response = await ask(client, session, conversation["id"], "How many leave days?")
    assert response.status_code == 201, response.text

    assert len(calls) == 1
    context = calls[0]["context"]
    assert context, "expected retrieval results inside the HR collection"
    for chunk in context:
        assert str(chunk.collection_id) == hr["id"], chunk
        assert str(chunk.collection_id) != finance["id"]
