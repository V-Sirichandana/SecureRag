"""FastEmbed semantic embedding provider tests — fully offline and mocked.

No model is downloaded: a small FastEmbed-compatible class supplies metadata
and deterministic vectors. The real provider class, metadata validation,
lazy loading/cache, dimension checks and error mapping are all exercised.
"""

from __future__ import annotations

import builtins

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError, ServiceNotConfiguredError
from app.services.ingestion import embeddings as embeddings_module
from app.services.ingestion.embeddings import (
    DEFAULT_FASTEMBED_MODEL,
    FastEmbedEmbeddingProvider,
    HashingEmbeddingProvider,
)
from app.services.rag import get_embedding_service

DIMENSION = 8


class FakeTextEmbedding:
    """Offline stand-in for ``fastembed.TextEmbedding``."""

    created = 0
    instances: list[FakeTextEmbedding] = []

    def __init__(self, *, model_name: str, **kwargs) -> None:
        self.model_name = model_name
        self.kwargs = kwargs
        self.passage_calls: list[list[str]] = []
        self.query_calls: list[str] = []
        type(self).created += 1
        type(self).instances.append(self)

    @classmethod
    def list_supported_models(cls):
        return [
            {"model": "fake/embed-small", "dim": DIMENSION, "size_in_GB": 0.01},
            {"model": "fake/embed-large", "dim": DIMENSION * 2, "size_in_GB": 0.02},
        ]

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [float(len(text) % 7 + 1.0)] * DIMENSION

    def passage_embed(self, texts):
        self.passage_calls.append(list(texts))
        return [self._vector(text) for text in texts]

    def query_embed(self, text):
        self.query_calls.append(text)
        return [self._vector(text)]


class SharedFakeTextEmbedding(FakeTextEmbedding):
    """A FastEmbed-namespaced double so the process-wide cache is exercised."""

    __module__ = "fastembed.tests.fake"


@pytest.fixture(autouse=True)
def _reset_fastembed(monkeypatch):
    FastEmbedEmbeddingProvider.clear_model_cache()
    monkeypatch.setattr(embeddings_module, "TextEmbedding", None)
    FakeTextEmbedding.created = 0
    FakeTextEmbedding.instances = []
    SharedFakeTextEmbedding.created = 0
    SharedFakeTextEmbedding.instances = []
    yield
    FastEmbedEmbeddingProvider.clear_model_cache()


def settings(*, model: str = "fake/embed-small", dimension: int = DIMENSION) -> Settings:
    return Settings(
        _env_file=None,
        embedding_provider="fastembed",
        embedding_model=model,
        embedding_dim=dimension,
    )


def provider(*, model: str = "fake/embed-small", dimension: int = DIMENSION):
    return FastEmbedEmbeddingProvider(model=model, dimension=dimension)


# ------------------------------------------------------------- hashing parity
async def test_hashing_provider_is_still_default_and_unchanged():
    assert Settings(_env_file=None).embedding_provider == "hashing"
    h = HashingEmbeddingProvider(dimension=48)
    first = await h.embed_documents(["monthly revenue report"])
    query = await h.embed_query("monthly revenue report")
    assert query == first[0]
    assert h.dimension == len(first[0]) == 48
    assert h.provider_name == "hashing"


# --------------------------------------------------------- metadata/validation
def test_factory_builds_fastembed_and_validates_metadata(monkeypatch):
    monkeypatch.setattr(embeddings_module, "TextEmbedding", FakeTextEmbedding)
    service = get_embedding_service(settings())

    assert isinstance(service, FastEmbedEmbeddingProvider)
    assert service.model_name == "fake/embed-small"
    assert service.dimension == DIMENSION
    assert FakeTextEmbedding.created == 0, "construction must not load the model"


def test_empty_model_uses_supported_default(monkeypatch):
    monkeypatch.setattr(embeddings_module, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(
        FakeTextEmbedding,
        "list_supported_models",
        classmethod(
            lambda cls: [{"model": DEFAULT_FASTEMBED_MODEL, "dim": 384}]
        ),
    )
    service = FastEmbedEmbeddingProvider(model="", dimension=384)
    assert service.model_name == DEFAULT_FASTEMBED_MODEL
    assert service.dimension == 384


def test_dimension_mismatch_is_rejected_before_model_load(monkeypatch):
    monkeypatch.setattr(embeddings_module, "TextEmbedding", FakeTextEmbedding)
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        provider(model="fake/embed-small", dimension=99)

    assert excinfo.value.status_code == 501
    assert "EMBEDDING_DIM=99" in excinfo.value.message
    assert f"{DIMENSION} dimensions" in excinfo.value.message
    assert FakeTextEmbedding.created == 0


def test_unsupported_model_is_rejected_before_model_load(monkeypatch):
    monkeypatch.setattr(embeddings_module, "TextEmbedding", FakeTextEmbedding)
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        provider(model="not/supported")

    assert excinfo.value.status_code == 501
    assert "not/supported" in excinfo.value.message
    assert FakeTextEmbedding.created == 0


def test_missing_dependency_is_configuration_error(monkeypatch):
    real_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fastembed" or name.startswith("fastembed."):
            raise ImportError("fastembed is not installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    monkeypatch.setattr(embeddings_module, "TextEmbedding", None)

    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        provider(model="fake/embed-small", dimension=DIMENSION)

    assert excinfo.value.status_code == 501
    assert "fastembed" in excinfo.value.message.lower()


# ------------------------------------------------------- lazy load and cache
async def test_model_is_lazy_and_cached_process_wide(monkeypatch):
    monkeypatch.setattr(embeddings_module, "TextEmbedding", SharedFakeTextEmbedding)
    first = provider()
    second = provider()

    assert SharedFakeTextEmbedding.created == 0
    assert await first.embed_documents([]) == []
    assert SharedFakeTextEmbedding.created == 0

    await first.embed_documents(["alpha"])
    assert SharedFakeTextEmbedding.created == 1

    await second.embed_documents(["beta"])
    assert SharedFakeTextEmbedding.created == 1, "second provider must reuse the model"
    assert first._encoder is second._encoder


# ----------------------------------------------- query/document consistency
async def test_query_and_documents_share_model_and_dimension(monkeypatch):
    monkeypatch.setattr(embeddings_module, "TextEmbedding", FakeTextEmbedding)
    service = provider()

    documents = await service.embed_documents(["alpha beta", "gamma"])
    query = await service.embed_query("alpha beta")

    assert FakeTextEmbedding.created == 1
    assert len(FakeTextEmbedding.instances) == 1
    model = FakeTextEmbedding.instances[0]
    assert model.model_name == "fake/embed-small"
    assert len(documents) == 2
    assert all(len(vector) == service.dimension == DIMENSION for vector in documents)
    assert len(query) == service.dimension == DIMENSION
    assert model.passage_calls == [["alpha beta", "gamma"]]
    assert model.query_calls == ["alpha beta"]
    assert query == documents[0], "the fake uses the same deterministic vector space"


# ---------------------------------------------------------- safe output errors
async def test_document_dimension_mismatch_is_service_unavailable(monkeypatch):
    class WrongDimension(FakeTextEmbedding):
        def passage_embed(self, texts):
            return [[1.0, 2.0, 3.0] for _ in texts]

    monkeypatch.setattr(embeddings_module, "TextEmbedding", WrongDimension)
    service = provider()

    with pytest.raises(AppError) as excinfo:
        await service.embed_documents(["alpha"])

    assert excinfo.value.status_code == 503
    assert "unexpected dimension" in excinfo.value.message.lower()


async def test_query_dimension_mismatch_is_service_unavailable(monkeypatch):
    class WrongQueryDimension(FakeTextEmbedding):
        def query_embed(self, text):
            return [[1.0, 2.0]]

    monkeypatch.setattr(embeddings_module, "TextEmbedding", WrongQueryDimension)
    service = provider()

    with pytest.raises(AppError) as excinfo:
        await service.embed_query("alpha")

    assert excinfo.value.status_code == 503


async def test_non_finite_output_is_rejected(monkeypatch):
    class NonFinite(FakeTextEmbedding):
        def passage_embed(self, texts):
            return [[float("nan")] * DIMENSION for _ in texts]

    monkeypatch.setattr(embeddings_module, "TextEmbedding", NonFinite)
    service = provider()

    with pytest.raises(AppError) as excinfo:
        await service.embed_documents(["alpha"])

    assert excinfo.value.status_code == 503
    assert "invalid value" in excinfo.value.message.lower()


async def test_model_load_failure_is_safe_503(monkeypatch):
    class BrokenModel(FakeTextEmbedding):
        def __init__(self, **kwargs):
            raise RuntimeError("download failed secret=sk-EMBED-LEAK")

    monkeypatch.setattr(embeddings_module, "TextEmbedding", BrokenModel)
    service = provider()

    with pytest.raises(AppError) as excinfo:
        await service.embed_documents(["alpha"])

    assert excinfo.value.status_code == 503
    assert "could not be loaded" in excinfo.value.message.lower()
    assert "sk-embed-leak" not in excinfo.value.message.lower()
    assert "traceback" not in excinfo.value.message.lower()


async def test_inference_failure_is_safe_503(monkeypatch):
    class BrokenInference(FakeTextEmbedding):
        def passage_embed(self, texts):
            raise RuntimeError("onnx blew up secret=sk-EMBED-LEAK")

    monkeypatch.setattr(embeddings_module, "TextEmbedding", BrokenInference)
    service = provider()

    with pytest.raises(AppError) as excinfo:
        await service.embed_documents(["alpha"])

    assert excinfo.value.status_code == 503
    assert "sk-embed-leak" not in excinfo.value.message.lower()
