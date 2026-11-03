"""FastEmbed neural reranker: factory wiring, scoring, limits and failures.

These tests never download a model. A small in-process encoder is injected
through the provider's ``encoder_factory`` seam or by patching the lazy import
helper, so the suite stays offline while still exercising the real provider
class, factory registration and retriever authorization pipeline.
"""

from __future__ import annotations

import builtins

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError, ServiceNotConfiguredError
from app.services.rag import get_reranker
from app.services.rag import reranker as reranker_module
from app.services.rag.base import RetrievedChunk
from app.services.rag.reranker import (
    DEFAULT_FASTEMBED_MODEL,
    FASTEMBED_PROVIDER_NAME,
    NEURAL_PROVIDER_NAME,
    FastEmbedReranker,
    HeuristicReranker,
)
from app.services.rag.retriever import MAX_CANDIDATES
from tests.conftest import create_collection
from tests.test_retrieval import document_ids, retrieve, tenant_of, upload


class FakeEncoder:
    """Offline stand-in for ``fastembed.rerank.cross_encoder.TextCrossEncoder``."""

    def __init__(self, *, model_name: str, **_kwargs) -> None:
        self.model_name = model_name
        self.calls: list[list[str]] = []

    def rerank(self, query: str, documents):
        docs = list(documents)
        self.calls.append(docs)
        terms = set(query.casefold().split())
        return [float(len(terms & set(doc.casefold().split()))) for doc in docs]


class RecordingFactory:
    """Create FakeEncoder instances and expose them for assertions."""

    def __init__(self, encoder_cls=FakeEncoder) -> None:
        self.encoder_cls = encoder_cls
        self.instances: list[FakeEncoder] = []

    def __call__(self, *, model_name: str, **kwargs):
        encoder = self.encoder_cls(model_name=model_name, **kwargs)
        self.instances.append(encoder)
        return encoder


@pytest.fixture(autouse=True)
def _clear_model_cache():
    FastEmbedReranker.clear_model_cache()
    yield
    FastEmbedReranker.clear_model_cache()


def chunks(*specs: tuple[str, float, str]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            text=text,
            score=score,
            document_id="doc-1",
            chunk_id=chunk_id,
        )
        for chunk_id, score, text in specs
    ]


# ----------------------------------------------------- heuristic stays intact
async def test_heuristic_provider_remains_functional():
    candidates = chunks(
        ("a", 0.2, "alpha beta"),
        ("b", 0.9, "beta only"),
        ("c", 0.8, "unrelated content"),
    )

    result = await HeuristicReranker().rerank(
        query="alpha beta", chunks=candidates, top_k=2
    )

    assert [chunk.chunk_id for chunk in result] == ["a", "b"]
    assert [chunk.score for chunk in result] == [0.2, 0.9]
    assert all(chunk.rerank_score is not None for chunk in result)
    assert all(chunk.rerank_score is None for chunk in candidates)  # never mutated


# ------------------------------------------------------------- registration
def test_fastembed_provider_is_registered(monkeypatch):
    monkeypatch.setattr(reranker_module, "_import_text_cross_encoder", lambda: FakeEncoder)

    settings = Settings(
        _env_file=None,
        reranker_provider=FASTEMBED_PROVIDER_NAME,
        reranker_model="test/fake-reranker",
    )
    provider = get_reranker(settings)

    assert isinstance(provider, FastEmbedReranker)
    assert provider.model_name == "test/fake-reranker"


def test_neural_alias_resolves_to_fastembed_provider(monkeypatch):
    monkeypatch.setattr(reranker_module, "_import_text_cross_encoder", lambda: FakeEncoder)

    provider = get_reranker(
        Settings(_env_file=None, reranker_provider=NEURAL_PROVIDER_NAME)
    )

    assert isinstance(provider, FastEmbedReranker)
    assert provider.model_name == DEFAULT_FASTEMBED_MODEL


# --------------------------------------------------------- neural ordering
async def test_neural_scores_reorder_without_touching_vector_scores():
    factory = RecordingFactory()

    class ScriptedEncoder(FakeEncoder):
        def rerank(self, query: str, documents):
            docs = list(documents)
            self.calls.append(docs)
            # deliberately not correlated with the vector score
            return iter([0.1, 2.0, 1.0])

    factory.encoder_cls = ScriptedEncoder
    provider = FastEmbedReranker(model="test/fake-reranker", encoder_factory=factory)
    candidates = chunks(
        ("a", 0.95, "alpha"),
        ("b", 0.10, "beta"),
        ("c", 0.50, "gamma"),
    )

    result = await provider.rerank(query="anything", chunks=candidates, top_k=2)

    assert factory.instances, "the model must be created lazily for the first call"
    assert [chunk.chunk_id for chunk in result] == ["b", "c"]
    assert [chunk.rerank_score for chunk in result] == [2.0, 1.0]
    assert [chunk.score for chunk in result] == [0.10, 0.50]  # vector score survives
    assert all(chunk.rerank_score is None for chunk in candidates)


async def test_neural_ties_keep_original_vector_order():
    class TiedEncoder(FakeEncoder):
        def rerank(self, query: str, documents):
            self.calls.append(list(documents))
            return [1.0 for _ in documents]

    provider = FastEmbedReranker(
        model="test/fake-reranker", encoder_factory=RecordingFactory(TiedEncoder)
    )
    candidates = chunks(
        ("low", 0.2, "alpha"),
        ("high", 0.9, "beta"),
        ("middle", 0.5, "gamma"),
    )

    result = await provider.rerank(query="anything", chunks=candidates, top_k=3)

    assert [chunk.chunk_id for chunk in result] == ["high", "middle", "low"]


# ------------------------------------------------ lazy loading and limits
async def test_model_loading_is_lazy_and_empty_pool_never_loads():
    factory = RecordingFactory()
    provider = FastEmbedReranker(model="test/fake-reranker", encoder_factory=factory)

    assert factory.instances == []
    assert await provider.rerank(query="anything", chunks=[], top_k=5) == []
    assert factory.instances == []

    await provider.rerank(
        query="anything",
        chunks=chunks(("a", 0.9, "alpha")),
        top_k=1,
    )
    assert len(factory.instances) == 1


async def test_candidate_limit_is_never_above_40():
    assert MAX_CANDIDATES == 40
    factory = RecordingFactory()
    provider = FastEmbedReranker(model="test/fake-reranker", encoder_factory=factory)
    candidates = chunks(
        *[(f"c{index}", 1.0 - index / 1000, f"text {index}") for index in range(100)]
    )

    await provider.rerank(query="text", chunks=candidates, top_k=5)

    assert len(factory.instances[0].calls[0]) == MAX_CANDIDATES
    assert factory.instances[0].calls[0] == [chunk.text for chunk in candidates[:40]]


# --------------------------------------------------------- failure handling
def test_missing_fastembed_dependency_is_configuration_error(monkeypatch):
    real_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fastembed" or name.startswith("fastembed."):
            raise ImportError("fastembed is not installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    monkeypatch.setattr(reranker_module, "TextCrossEncoder", None)

    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        FastEmbedReranker(model=DEFAULT_FASTEMBED_MODEL)

    assert excinfo.value.status_code == 501
    assert "fastembed" in excinfo.value.message.lower()


def test_unsupported_model_is_rejected_before_loading(monkeypatch):
    class OnlyOneModel:
        @classmethod
        def list_supported_models(cls):
            return [{"model": "allowed/model"}]

    monkeypatch.setattr(reranker_module, "_import_text_cross_encoder", lambda: OnlyOneModel)

    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        FastEmbedReranker(model="not-allowed/model")

    assert excinfo.value.status_code == 501
    assert "not a supported fastembed reranker model" in excinfo.value.message.lower()


async def test_model_value_error_is_configuration_error():
    def broken_factory(**_kwargs):
        raise ValueError("Model bad/model is not supported in TextCrossEncoder.")

    provider = FastEmbedReranker(model="bad/model", encoder_factory=broken_factory)

    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        await provider.rerank(
            query="anything",
            chunks=chunks(("a", 0.9, "alpha")),
            top_k=1,
        )

    assert excinfo.value.status_code == 501
    assert "bad/model" in excinfo.value.message


async def test_model_loading_error_is_service_unavailable():
    def broken_factory(**_kwargs):
        raise RuntimeError("download failed with secret=sk-MODEL-LEAK")

    provider = FastEmbedReranker(model="test/fake-reranker", encoder_factory=broken_factory)

    with pytest.raises(AppError) as excinfo:
        await provider.rerank(
            query="anything",
            chunks=chunks(("a", 0.9, "alpha")),
            top_k=1,
        )

    assert excinfo.value.code == "SERVICE_UNAVAILABLE"
    assert excinfo.value.status_code == 503
    assert "sk-model-leak" not in excinfo.value.message.lower()
    assert "traceback" not in excinfo.value.message.lower()


async def test_malformed_neural_scores_are_service_unavailable():
    class ShortEncoder(FakeEncoder):
        def rerank(self, query: str, documents):
            self.calls.append(list(documents))
            return [1.0]  # one score for two documents

    provider = FastEmbedReranker(
        model="test/fake-reranker", encoder_factory=RecordingFactory(ShortEncoder)
    )

    with pytest.raises(AppError) as excinfo:
        await provider.rerank(
            query="anything",
            chunks=chunks(("a", 0.9, "alpha"), ("b", 0.8, "beta")),
            top_k=1,
        )

    assert excinfo.value.code == "SERVICE_UNAVAILABLE"
    assert excinfo.value.status_code == 503


# ------------------------------------ authorization happens before reranking
async def test_neural_reranker_only_sees_authorized_chunks(
    app, actor_factory, monkeypatch
):
    class RecordingEncoder(FakeEncoder):
        seen: list[list[str]] = []

        def rerank(self, query: str, documents):
            docs = list(documents)
            type(self).seen.append(docs)
            return super().rerank(query, docs)

    RecordingEncoder.seen = []
    monkeypatch.setattr(
        reranker_module, "_import_text_cross_encoder", lambda: RecordingEncoder
    )
    app.state.settings.reranker_provider = FASTEMBED_PROVIDER_NAME
    app.state.settings.reranker_model = "test/fake-reranker"

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
        content=b"salary review guidelines for the engineering org",
    )
    foreign = await upload(
        outsider_client,
        outsider_session,
        collection_id=outsider_collection["id"],
        filename="foreign.txt",
        content=b"salary band revision confidential engineering 2026",
    )

    response = await retrieve(member_client, member_session, query=query, top_k=10)

    assert response.status_code == 200, response.text
    assert RecordingEncoder.seen, "the neural reranker must have been invoked"
    seen_documents = [document for call in RecordingEncoder.seen for document in call]
    # Only chunk text is sent to the model — never document metadata or ids.
    assert not any("confidential engineering 2026" in text for text in seen_documents)
    assert any("salary review guidelines" in text for text in seen_documents)
    assert document_ids(response) == {shared["id"]}
    assert tenant_of(member_session) == owner_session["user"]["organizationId"]
    assert secret["id"] != shared["id"] != foreign["id"]
