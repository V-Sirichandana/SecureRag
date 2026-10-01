"""RAG service factory.

Vendor-specific implementations register here when the RAG phase lands.
Until then every factory raises ``SERVICE_NOT_CONFIGURED`` instead of
pretending to work.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import ServiceNotConfiguredError
from app.services.rag.base import (
    DocumentProcessor,
    EmbeddingService,
    LLMProvider,
    Reranker,
    Retriever,
    VectorStore,
)

# filled in by provider modules as they are implemented, e.g.
#   _LLM_PROVIDERS["openai"] = OpenAIProvider
_LLM_PROVIDERS: dict[str, type] = {}
_EMBEDDING_PROVIDERS: dict[str, type] = {}
_PROCESSORS: dict[str, type] = {}


def get_document_processor(settings: Settings) -> DocumentProcessor:
    raise ServiceNotConfiguredError(
        "SERVICE_NOT_CONFIGURED",
        "Document ingestion arrives with the RAG phase (no processor configured).",
    )


def get_embedding_service(settings: Settings) -> EmbeddingService:
    raise ServiceNotConfiguredError(
        "SERVICE_NOT_CONFIGURED",
        "Embedding service is not configured yet (RAG phase).",
    )


def get_vector_store(settings: Settings) -> VectorStore:
    if not settings.qdrant_url:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED", "QDRANT_URL is not configured."
        )
    raise ServiceNotConfiguredError(
        "SERVICE_NOT_CONFIGURED", "Vector store integration arrives with the RAG phase."
    )


def get_retriever(settings: Settings) -> Retriever:
    raise ServiceNotConfiguredError(
        "SERVICE_NOT_CONFIGURED", "Retriever arrives with the RAG phase."
    )


def get_reranker(settings: Settings) -> Reranker:
    raise ServiceNotConfiguredError(
        "SERVICE_NOT_CONFIGURED", "Reranker arrives with the RAG phase."
    )


def get_llm_provider(settings: Settings) -> LLMProvider:
    if not settings.llm_provider:
        raise ServiceNotConfiguredError("SERVICE_NOT_CONFIGURED", "LLM_PROVIDER is not set.")
    provider = _LLM_PROVIDERS.get(settings.llm_provider.lower())
    if provider is None:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            f"LLM provider '{settings.llm_provider}' has no implementation yet.",
        )
    return provider(settings)  # type: ignore[call-arg]


__all__ = [
    "DocumentProcessor",
    "EmbeddingService",
    "LLMProvider",
    "Reranker",
    "Retriever",
    "VectorStore",
    "get_document_processor",
    "get_embedding_service",
    "get_llm_provider",
    "get_reranker",
    "get_retriever",
    "get_vector_store",
]
