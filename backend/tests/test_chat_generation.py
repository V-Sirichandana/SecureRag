"""M6.0 — real answer generation: configuration, grounding, citations, isolation.

The provider is mocked at exactly two boundaries, never on the network:

* endpoint tests register a fake in ``_LLM_PROVIDERS`` — the registry the
  ``get_llm_provider`` factory resolves — so the whole route → chat service →
  retrieval → context handed to the provider path is exercised for real;
* provider unit tests inject ``httpx.MockTransport`` into the concrete
  provider to exercise request shaping, configuration errors, timeouts and
  upstream error mapping.

No test requires a real API key or an external LLM service.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.config import Settings
from app.core.exceptions import AppError, ServiceNotConfiguredError
from app.db.database import create_all, drop_all
from app.main import create_app
from app.services.rag import _LLM_PROVIDERS
from app.services.rag.answer import build_citations
from app.services.rag.base import GenerationResult, RetrievedChunk
from app.services.rag.llm import OpenAIChatProvider
from tests.conftest import auth, create_collection, create_document

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
async def create_conversation(client, session, **payload) -> dict:
    response = await client.post(
        "/chat/conversations", json={"title": "Policy chat", **payload}, headers=auth(session)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def ask(client, session, conversation_id, question="What does the policy say?"):
    return await client.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"role": "user", "content": question},
        headers=auth(session),
    )


async def upload(
    client,
    session,
    *,
    collection_id,
    filename,
    content,
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


async def messages_of(client, session, conversation_id) -> list[dict]:
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
    answer: str = "This is a generated answer.",
    error: Exception | None = None,
    provider_citations: list | None = None,
    calls: list | None = None,
) -> list:
    """Point the app at a fake registered at the provider-registry boundary.

    Configures ``LLM_PROVIDER=openai`` (the name the factory resolves) AND
    swaps the registry entry, so the route → factory → provider path runs
    exactly as in production — only the provider implementation is fake.
    """
    settings = app.state.settings
    settings.llm_provider = "openai"
    settings.llm_model = "test-model"
    settings.llm_api_key = FAKE_KEY
    recorded = calls if calls is not None else []

    class FakeProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def generate(self, *, system, prompt, context, max_tokens=1024):
            recorded.append(
                {"system": system, "prompt": prompt, "context": list(context)}
            )
            if error is not None:
                raise error
            return GenerationResult(
                content=answer,
                citations=list(provider_citations or []),
                model="fake-model",
                latency_ms=12,
                token_count=7,
            )

    monkeypatch.setitem(_LLM_PROVIDERS, "openai", FakeProvider)
    return recorded


class ScriptedStore:
    """Returns a fixed candidate list regardless of tenant — the adversarial
    case — and records every search it receives."""

    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.calls: list[dict] = []

    async def search(
        self,
        *,
        vector,
        tenant_id,
        top_k=8,
        extra_filter=None,
        collection_id=None,
        document_ids=None,
        **kwargs,
    ) -> list[RetrievedChunk]:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "top_k": top_k,
                "extra_filter": extra_filter,
            }
        )
        return list(self.chunks)[:top_k]

    async def upsert_chunks(self, **kwargs):  # pragma: no cover - never used
        raise NotImplementedError

    async def delete_document(self, **kwargs):  # pragma: no cover - never used
        raise NotImplementedError


def chunk_for(
    document: dict,
    *,
    collection_id: str,
    text: str,
    filename: str,
    score: float = 0.9,
    page: int = 1,
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        score=score,
        document_id=document["id"],
        collection_id=collection_id,
        page_number=page,
        quote=text[:200],
        chunk_id=str(uuid.uuid4()),
        filename=filename,
        metadata={"document_name": filename},
    )


def provider_settings(**overrides) -> Settings:
    values = dict(
        _env_file=None,
        llm_provider="openai",
        llm_model="test-model",
        llm_api_key=FAKE_KEY,
        llm_base_url="https://api.openai.com/v1",
        llm_timeout_seconds=5.0,
    )
    values.update(overrides)
    return Settings(**values)


# ------------------------------------------- 1. missing provider configuration
async def test_question_without_provider_config_returns_501(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    conversation = await create_conversation(client, session)

    response = await ask(client, session, conversation["id"])

    assert response.status_code == 501, response.text
    assert response.json()["error"]["code"] == "SERVICE_NOT_CONFIGURED"
    assert "LLM_PROVIDER" in response.json()["error"]["message"]
    # nothing is persisted and no QUERY audit fires when generation cannot run
    assert await messages_of(client, session, conversation["id"]) == []
    assert await query_audits(client, session) == []


async def test_unknown_provider_name_returns_501(app, actor_factory):
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    conversation = await create_conversation(client, session)
    app.state.settings.llm_provider = "does-not-exist"

    response = await ask(client, session, conversation["id"])

    assert response.status_code == 501, response.text
    assert "does-not-exist" in response.json()["error"]["message"]


async def test_missing_model_or_api_key_returns_501(app, actor_factory):
    """A registered provider with incomplete configuration fails closed (501)."""
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    conversation = await create_conversation(client, session)
    settings = app.state.settings
    settings.llm_provider = "openai"  # the REAL provider validates its own config
    settings.llm_model = ""
    settings.llm_api_key = FAKE_KEY

    response = await ask(client, session, conversation["id"])

    assert response.status_code == 501, response.text
    assert response.json()["error"]["code"] == "SERVICE_NOT_CONFIGURED"
    assert "LLM_MODEL" in response.json()["error"]["message"]
    assert await messages_of(client, session, conversation["id"]) == []


async def test_assistant_role_persistence_needs_no_provider(app, actor_factory):
    """Backward compatibility: role="assistant" stays a plain persistence call."""
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    conversation = await create_conversation(client, session)

    response = await client.post(
        f"/chat/conversations/{conversation['id']}/messages",
        json={
            "role": "assistant",
            "content": "Imported historical answer.",
            "citations": [{"index": 1, "documentId": "doc-1"}],
            "model": "old-model",
        },
        headers=auth(session),
    )

    assert response.status_code == 201, response.text
    assert response.json()["role"] == "assistant"
    assert response.json()["content"] == "Imported historical answer."
    assert response.json()["citations"] == [{"index": 1, "documentId": "doc-1"}]


# ------------------------------------------------------- 2. provider (mocked HTTP)
def test_provider_requires_model_configuration():
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        OpenAIChatProvider(provider_settings(llm_model=""))
    assert excinfo.value.status_code == 501
    assert "LLM_MODEL" in excinfo.value.message


def test_provider_requires_api_key_against_default_endpoint():
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        OpenAIChatProvider(provider_settings(llm_api_key=""))
    assert excinfo.value.status_code == 501
    assert "LLM_API_KEY" in excinfo.value.message


def test_provider_allows_keyless_custom_endpoint():
    provider = OpenAIChatProvider(
        provider_settings(llm_api_key="", llm_base_url="http://localhost:11434/v1")
    )
    assert provider.api_key == ""


async def test_provider_success_renders_numbered_context():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "model": "upstream-model",
                "choices": [{"message": {"content": "Employees receive 20 days. [1]"}}],
                "usage": {"total_tokens": 42},
            },
        )

    provider = OpenAIChatProvider(
        provider_settings(), transport=httpx.MockTransport(handler)
    )
    chunk = RetrievedChunk(
        text="Full-time employees receive 20 days of annual leave.",
        score=0.9,
        document_id=str(uuid.uuid4()),
        chunk_id=str(uuid.uuid4()),
        filename="handbook.pdf",
        page_number=3,
    )

    result = await provider.generate(
        system="system instructions", prompt="How much leave?", context=[chunk]
    )

    assert result.content == "Employees receive 20 days. [1]"
    assert result.model == "upstream-model"
    assert result.token_count == 42
    assert result.citations == []  # providers never contribute citation metadata
    assert result.latency_ms >= 0

    request = captured["request"]
    assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    body = json.loads(request.content)
    assert body["messages"][0]["content"] == "system instructions"
    user_message = body["messages"][1]["content"]
    assert "[1] handbook.pdf, page 3" in user_message
    assert "Question: How much leave?" in user_message


async def test_provider_timeout_maps_to_service_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream read timed out")

    provider = OpenAIChatProvider(
        provider_settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AppError) as excinfo:
        await provider.generate(system="s", prompt="q", context=[])
    assert excinfo.value.code == "SERVICE_UNAVAILABLE"
    assert excinfo.value.status_code == 503
    assert "timed out" in excinfo.value.message


async def test_provider_http_error_never_surfaces_upstream_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "upstream-secret-detail"})

    provider = OpenAIChatProvider(
        provider_settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AppError) as excinfo:
        await provider.generate(system="s", prompt="q", context=[])
    assert excinfo.value.status_code == 503
    assert "HTTP 500" in excinfo.value.message
    assert "upstream-secret-detail" not in excinfo.value.message


async def test_provider_malformed_response_maps_to_service_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    provider = OpenAIChatProvider(
        provider_settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AppError) as excinfo:
        await provider.generate(system="s", prompt="q", context=[])
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "SERVICE_UNAVAILABLE"


def test_provider_accepts_complete_configuration() -> None:
    provider = OpenAIChatProvider(provider_settings())
    assert provider.model == "test-model"
    assert provider.api_key == FAKE_KEY
    assert provider.base_url == "https://api.openai.com/v1"


async def test_provider_connection_failure_maps_to_service_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = OpenAIChatProvider(
        provider_settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AppError) as excinfo:
        await provider.generate(system="s", prompt="q", context=[])
    assert excinfo.value.code == "SERVICE_UNAVAILABLE"
    assert excinfo.value.status_code == 503
    assert "timed out" not in excinfo.value.message.lower()


async def test_provider_uses_configured_base_url_for_chat_completions() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200, json={"model": "m", "choices": [{"message": {"content": "ok"}}]}
        )

    provider = OpenAIChatProvider(
        provider_settings(llm_api_key=FAKE_KEY, llm_base_url="http://localhost:11434/v1"),
        transport=httpx.MockTransport(handler),
    )
    result = await provider.generate(system="s", prompt="q", context=[])
    assert str(captured["url"]).endswith("/v1/chat/completions")
    assert result.content == "ok"


async def test_provider_missing_choices_maps_to_service_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "upstream-model", "choices": []})

    provider = OpenAIChatProvider(
        provider_settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AppError) as excinfo:
        await provider.generate(system="s", prompt="q", context=[])
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "SERVICE_UNAVAILABLE"


def test_provider_configuration_errors_do_not_include_credentials() -> None:
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        OpenAIChatProvider(provider_settings(llm_model="", llm_api_key="sk-secret-value"))
    assert excinfo.value.status_code == 501
    assert "sk-secret-value" not in excinfo.value.message


# --------------------------------------------- 4. successful answer + citations
async def test_successful_question_returns_answer_and_citations(
    app, actor_factory, monkeypatch
):
    calls = install_fake_provider(
        app,
        monkeypatch, answer="Full-time employees receive 20 days of annual leave. [1]"
    )
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Policies")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="handbook.txt",
        content=b"Full-time employees receive 20 days of annual leave each calendar year.",
    )
    conversation = await create_conversation(client, session)

    response = await ask(client, session, conversation["id"], "How much annual leave?")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "assistant"
    assert body["content"] == "Full-time employees receive 20 days of annual leave. [1]"
    assert body["model"] == "fake-model"
    assert body["latencyMs"] == 12
    assert body["tokenCount"] == 7

    # the provider received the question and ONLY the authorized chunk
    assert len(calls) == 1
    assert calls[0]["prompt"] == "How much annual leave?"
    context = calls[0]["context"]
    assert [chunk.document_id for chunk in context] == [document["id"]]

    citations = body["citations"]
    assert len(citations) == 1
    citation = citations[0]
    assert citation["index"] == 1
    assert citation["documentId"] == document["id"]
    assert citation["documentName"] == "handbook.txt"
    assert citation["collectionName"] == "Policies"
    assert citation["pageNumber"] >= 1
    assert citation["chunkId"] == context[0].chunk_id
    assert citation["quote"]

    # both messages persisted, question first, title updated from the question
    messages = await messages_of(client, session, conversation["id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "How much annual leave?"
    assert messages[1]["citations"] == citations


# ---------------------------------- 5./9. citations only from retrieved chunks
async def test_citations_come_only_from_retrieved_chunks(app, actor_factory, monkeypatch):
    calls = install_fake_provider(
        app,
        monkeypatch,
        answer="Grounded claim [1]. Invented reference [9].",
        # a hostile/buggy provider cannot inject citation metadata either
        provider_citations=[
            {"index": 9, "documentId": "evil-doc", "documentName": "Fabricated.pdf"}
        ],
    )
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Knowledge")
    first = await create_document(
        client, session, collection_id=collection["id"], name="First.pdf"
    )
    second = await create_document(
        client, session, collection_id=collection["id"], name="Second.pdf"
    )
    conversation = await create_conversation(client, session)

    store = ScriptedStore(
        [
            chunk_for(
                first,
                collection_id=collection["id"],
                text="First document content.",
                filename="First.pdf",
            ),
            chunk_for(
                second,
                collection_id=collection["id"],
                text="Second document content.",
                filename="Second.pdf",
                score=0.8,
            ),
        ]
    )
    monkeypatch.setattr(app.state, "vector_store", store)

    response = await ask(client, session, conversation["id"], "Summarise both documents.")

    assert response.status_code == 201, response.text
    assert len(calls[0]["context"]) == 2  # both authorized chunks reached the model
    citations = response.json()["citations"]
    # only the in-range marker becomes a citation; [9] is dropped, and the
    # provider-supplied "Fabricated.pdf" metadata never appears anywhere
    assert [citation["index"] for citation in citations] == [1]
    assert {citation["documentId"] for citation in citations} == {first["id"]}
    assert "Fabricated.pdf" not in response.text
    assert "evil-doc" not in response.text
    # the second chunk was in context but never cited → no citation for it
    assert second["id"] not in {citation["documentId"] for citation in citations}

    persisted = await messages_of(client, session, conversation["id"])
    assert persisted[1]["citations"] == citations


# ------------------------------------- 6. unauthorized chunks never reach LLM
async def test_unauthorized_chunks_never_reach_the_provider(
    app, actor_factory, monkeypatch
):
    calls = install_fake_provider(app, monkeypatch, answer="Only what you may read. [1]")
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
    secret = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="salary.txt",
        classification="confidential",
    )
    shared = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="handbook.txt",
        classification="internal",
    )

    # the store ignores every fence and hands back BOTH documents, ranked with
    # the unauthorized one first — authorization must happen downstream
    store = ScriptedStore(
        [
            chunk_for(
                secret,
                collection_id=collection["id"],
                text="Confidential salary bands.",
                filename="salary.txt",
                score=0.99,
            ),
            chunk_for(
                shared,
                collection_id=collection["id"],
                text="Shared onboarding handbook.",
                filename="handbook.txt",
                score=0.9,
            ),
        ]
    )
    monkeypatch.setattr(app.state, "vector_store", store)

    conversation = await create_conversation(member_client, member_session)
    response = await ask(member_client, member_session, conversation["id"], "salary bands?")

    assert response.status_code == 201, response.text
    assert len(calls) == 1
    context_ids = [chunk.document_id for chunk in calls[0]["context"]]
    assert context_ids == [shared["id"]]
    assert secret["id"] not in context_ids

    citations = response.json()["citations"]
    assert {citation["documentId"] for citation in citations} == {shared["id"]}
    assert "salary.txt" not in response.text


async def test_hybrid_mode_unauthorized_candidates_never_reach_the_provider(
    app, actor_factory, monkeypatch
):
    """Hybrid lexical candidates obey the same authorization boundary as vectors."""
    app.state.settings.retrieval_mode = "hybrid"
    calls = install_fake_provider(app, monkeypatch, answer="Only the handbook. [1]")
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    member_client, member_session = await actor_factory(
        name="Mia Member",
        email="mia@acme.com",
        invited_by=(owner_client, owner_session),
        role="member",
    )
    collection = await create_collection(owner_client, owner_session, name="Hybrid Mixed")
    secret = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="salary.txt",
        content=b"Confidential salary bands and compensation details.",
        classification="confidential",
    )
    shared = await upload(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        filename="handbook.txt",
        content=b"Shared salary bands policy for the onboarding handbook.",
        classification="internal",
    )

    # adversarial vector source: both documents, secret ranked first
    store = ScriptedStore(
        [
            chunk_for(
                secret,
                collection_id=collection["id"],
                text="Confidential salary bands and compensation details.",
                filename="salary.txt",
                score=0.99,
            ),
            chunk_for(
                shared,
                collection_id=collection["id"],
                text="Shared salary bands policy for the onboarding handbook.",
                filename="handbook.txt",
                score=0.9,
            ),
        ]
    )
    monkeypatch.setattr(app.state, "vector_store", store)

    conversation = await create_conversation(member_client, member_session)
    response = await ask(member_client, member_session, conversation["id"], "salary bands")

    assert response.status_code == 201, response.text
    assert len(calls) == 1
    context_ids = [chunk.document_id for chunk in calls[0]["context"]]
    assert shared["id"] in context_ids
    assert secret["id"] not in context_ids

    citations = response.json()["citations"]
    assert {citation["documentId"] for citation in citations} <= {shared["id"]}
    assert "salary.txt" not in response.text


# ------------------------------------------------- 7. tenant isolation preserved
async def test_tenant_isolation_is_preserved_for_generation(
    app, actor_factory, monkeypatch
):
    calls = install_fake_provider(app, monkeypatch, answer="Tenant A answer. [1]")
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    collection_a = await create_collection(client_a, session_a, name="Acme Files")
    collection_b = await create_collection(client_b, session_b, name="Globex Files")
    document_a = await create_document(
        client_a, session_a, collection_id=collection_a["id"], name="acme.txt"
    )
    document_b = await create_document(
        client_b, session_b, collection_id=collection_b["id"], name="globex.txt"
    )

    store = ScriptedStore(
        [
            chunk_for(
                document_b,
                collection_id=collection_b["id"],
                text="Globex-only content.",
                filename="globex.txt",
                score=0.99,
            ),
            chunk_for(
                document_a,
                collection_id=collection_a["id"],
                text="Acme-only content.",
                filename="acme.txt",
                score=0.9,
            ),
        ]
    )
    monkeypatch.setattr(app.state, "vector_store", store)

    conversation_a = await create_conversation(client_a, session_a)
    response_a = await ask(client_a, session_a, conversation_a["id"], "What are the details?")

    assert response_a.status_code == 201, response_a.text
    # server-derived tenant fence reached the store
    assert store.calls[0]["tenant_id"] == session_a["user"]["organizationId"]
    assert [chunk.document_id for chunk in calls[0]["context"]] == [document_a["id"]]
    assert document_b["id"] not in {
        citation["documentId"] for citation in response_a.json()["citations"]
    }

    # Bob cannot ask inside Alice's conversation — and never triggers generation
    response_b = await ask(client_b, session_b, conversation_a["id"], "Read Alice's chat")
    assert response_b.status_code == 404
    assert response_b.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
    assert len(calls) == 1


# ------------------------------------------------------- 8. empty retrieval context
async def test_empty_retrieval_context_returns_safe_answer(app, actor_factory, monkeypatch):
    calls = install_fake_provider(
        app,
        monkeypatch, answer="I could not find that in your indexed documents."
    )
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    conversation = await create_conversation(client, session)

    response = await ask(client, session, conversation["id"], "Anything at all?")

    assert response.status_code == 201, response.text
    assert response.json()["citations"] == []
    assert calls[0]["context"] == []
    messages = await messages_of(client, session, conversation["id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]


# ---------------------------------------------------- 3. provider failure handling
async def test_provider_failure_returns_503_and_persists_nothing(
    app, actor_factory, monkeypatch
):
    install_fake_provider(
        app,
        monkeypatch,
        error=AppError("SERVICE_UNAVAILABLE", "The answer provider timed out."),
    )
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    conversation = await create_conversation(client, session)

    response = await ask(client, session, conversation["id"])

    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert await messages_of(client, session, conversation["id"]) == []
    assert await query_audits(client, session) == []


async def test_unexpected_provider_exception_is_wrapped_without_leaking(
    app, actor_factory, monkeypatch
):
    install_fake_provider(app, monkeypatch, error=RuntimeError("kaboom api_key=sk-LEAK"))
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    conversation = await create_conversation(client, session)

    response = await ask(client, session, conversation["id"])

    assert response.status_code == 503, response.text
    body = response.text.lower()
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "kaboom" not in body
    assert "sk-leak" not in body
    assert await messages_of(client, session, conversation["id"]) == []


async def test_empty_model_answer_returns_503(app, actor_factory, monkeypatch):
    install_fake_provider(app, monkeypatch, answer="   \n  ")
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    conversation = await create_conversation(client, session)

    response = await ask(client, session, conversation["id"])

    assert response.status_code == 503, response.text
    assert "empty" in response.json()["error"]["message"].lower()
    assert await messages_of(client, session, conversation["id"]) == []


# ----------------------------------------- 10. persistence + QUERY audit behaviour
async def test_messages_and_query_audit_are_persisted(app, actor_factory, monkeypatch):
    install_fake_provider(app, monkeypatch, answer="Answer with a source. [1]")
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    collection = await create_collection(client, session, name="Policies")
    document = await create_document(
        client, session, collection_id=collection["id"], name="policy.txt"
    )
    conversation = await create_conversation(client, session, title="New conversation")
    question = "How many leave days does the policy allow?"

    store = ScriptedStore(
        [
            chunk_for(
                document,
                collection_id=collection["id"],
                text="The policy grants 20 leave days.",
                filename="policy.txt",
            )
        ]
    )
    monkeypatch.setattr(app.state, "vector_store", store)

    response = await ask(client, session, conversation["id"], question)
    assert response.status_code == 201, response.text

    messages = await messages_of(client, session, conversation["id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assistant = messages[1]
    assert assistant["model"] == "fake-model"
    assert assistant["latencyMs"] == 12
    assert assistant["tokenCount"] == 7
    assert assistant["feedback"] is None
    assert assistant["citations"][0]["documentId"] == document["id"]

    audits = await query_audits(client, session)
    assert len(audits) == 1
    assert audits[0]["action"] == "QUERY"
    assert audits[0]["resourceType"] == "conversation"
    assert audits[0]["resource"] == question[:48]

    # title seeded from the first question (existing behaviour)
    fetched = await client.get(
        f"/chat/conversations/{conversation['id']}", headers=auth(session)
    )
    assert fetched.json()["title"] == question[:48]


# ------------------------------------- rate limit preserved (retrieval bucket)
async def test_question_flow_shares_the_retrieval_rate_limit(
    app, actor_factory, monkeypatch
):
    calls = install_fake_provider(app, monkeypatch, answer="ok")
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    conversation = await create_conversation(client, session)

    allowed = [await ask(client, session, conversation["id"]) for _ in range(5)]
    assert [response.status_code for response in allowed] == [201] * 5

    blocked = await ask(client, session, conversation["id"])
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "TOO_MANY_REQUESTS"
    # the rejected request never reached the provider
    assert len(calls) == 5


# ------------------------------------- conversation collection narrows retrieval
async def test_conversation_collection_narrows_retrieval(app, actor_factory, monkeypatch):
    install_fake_provider(app, monkeypatch, answer="Scoped answer. [1]")
    client, session = await actor_factory(name="Ada", email="ada@example.com", org="Acme")
    hr = await create_collection(client, session, name="HR")
    finance = await create_collection(client, session, name="Finance")
    document = await create_document(
        client, session, collection_id=hr["id"], name="leave.txt"
    )
    conversation = await create_conversation(client, session, collection_id=hr["id"])

    store = ScriptedStore(
        [
            chunk_for(
                document,
                collection_id=hr["id"],
                text="Leave policy content.",
                filename="leave.txt",
            )
        ]
    )
    monkeypatch.setattr(app.state, "vector_store", store)

    response = await ask(client, session, conversation["id"], "leave policy?")
    assert response.status_code == 201, response.text
    # the conversation's server-validated collection narrows the vector filter
    assert store.calls[0]["extra_filter"] == {"collection_id": [hr["id"]]}
    assert finance["id"] not in str(store.calls[0]["extra_filter"])


# ------------------------------------- citation marker edge cases (unit level)
def _context_chunk(text: str, *, document_id: str, page: int) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        score=0.9,
        document_id=document_id,
        collection_id="col-1",
        page_number=page,
        quote=text[:200],
        chunk_id=str(uuid.uuid4()),
        filename=f"{document_id}.txt",
        metadata={},
    )


def test_duplicate_citation_markers_yield_a_single_citation() -> None:
    context = [
        _context_chunk("First passage.", document_id="doc-1", page=1),
        _context_chunk("Second passage.", document_id="doc-2", page=2),
    ]

    citations = build_citations("Reusing [1] then [1] again and [2] second.", context, {})

    assert [citation["index"] for citation in citations] == [1, 2]
    assert [citation["documentId"] for citation in citations] == ["doc-1", "doc-2"]


def test_citation_prefers_document_display_name_over_storage_filename() -> None:
    document_id = "36001ed5-cc73-452b-bca1-3b3a9701b115"
    chunk_id = "a995fff4-2962-5ec9-8d79-548c3466c0dd"
    chunk = RetrievedChunk(
        text="Project SecureRAG uses demo code SR-4821.",
        score=0.9,
        document_id=document_id,
        collection_id="col-demo",
        page_number=2,
        quote="Project SecureRAG uses demo code SR-4821.",
        chunk_id=chunk_id,
        filename="36001ed5-cc73-452b-bca1-3b3a9701b115.txt",
        metadata={"document_name": "SecureRAG Demo Document.txt"},
    )

    citations = build_citations(
        "The code is SR-4821 [1].",
        [chunk],
        {"col-demo": "SecureRag Demo"},
    )

    assert citations == [
        {
            "index": 1,
            "documentId": document_id,
            "documentName": "SecureRAG Demo Document.txt",
            "collectionId": "col-demo",
            "collectionName": "SecureRag Demo",
            "pageNumber": 2,
            "chunkId": chunk_id,
            "quote": "Project SecureRAG uses demo code SR-4821.",
        }
    ]


def test_answer_without_markers_or_context_yields_no_citations() -> None:
    context = [_context_chunk("Only passage.", document_id="doc-1", page=1)]

    # no markers in the answer → no citations, regardless of context
    assert build_citations("A source-free answer.", context, {}) == []
    # markers with an empty context can never resolve to a citation
    assert build_citations("Source [1] with empty context.", [], {}) == []
