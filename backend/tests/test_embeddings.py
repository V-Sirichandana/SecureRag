"""Embedding service: interface, vector shape, determinism, factory selection."""

from __future__ import annotations

import importlib.util
import math

import pytest

from app.core.config import Settings
from app.core.exceptions import ServiceNotConfiguredError
from app.services.ingestion.embeddings import HashingEmbeddingProvider
from app.services.rag import get_embedding_service


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_vector_shape_and_dimension():
    provider = HashingEmbeddingProvider(dimension=64)
    vectors = await provider.embed_documents(["alpha beta", "gamma"])
    assert len(vectors) == 2
    assert all(len(vector) == 64 for vector in vectors)
    assert provider.dimension == 64


async def test_embeddings_are_deterministic_and_normalized():
    provider = HashingEmbeddingProvider(dimension=48)
    first = await provider.embed_documents(["SecureRAG ingestion test"])
    second = await provider.embed_documents(["SecureRAG ingestion test"])
    assert first == second
    norm = math.sqrt(sum(value * value for value in first[0]))
    assert norm == pytest.approx(1.0, abs=1e-6)


async def test_query_embedding_matches_document_space():
    provider = HashingEmbeddingProvider(dimension=48)
    query = await provider.embed_query("monthly revenue report")
    document = (await provider.embed_documents(["monthly revenue report"]))[0]
    assert len(query) == provider.dimension
    assert query == document


async def test_similar_texts_score_higher_than_unrelated():
    provider = HashingEmbeddingProvider(dimension=128)
    query = await provider.embed_query("machine learning model training")
    related, unrelated = await provider.embed_documents(
        ["machine learning model training pipeline", "gardening tips for spring flowers"]
    )
    assert cosine(query, related) > cosine(query, unrelated)


def test_factory_returns_configured_provider():
    settings = Settings(embedding_provider="hashing", embedding_dim=96)
    service = get_embedding_service(settings)
    assert isinstance(service, HashingEmbeddingProvider)
    assert service.dimension == 96


def test_factory_rejects_unknown_provider():
    settings = Settings(embedding_provider="does-not-exist")
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        get_embedding_service(settings)
    assert excinfo.value.status_code == 501


def test_fastembed_requires_optional_dependency():
    if importlib.util.find_spec("fastembed") is not None:
        pytest.skip("fastembed is installed")
    settings = Settings(embedding_provider="fastembed")
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        get_embedding_service(settings)
    assert "fastembed" in str(excinfo.value)
