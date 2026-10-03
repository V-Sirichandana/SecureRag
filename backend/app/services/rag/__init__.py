"""RAG service factory.

Provider implementations register behind the protocols in
``app.services.rag.base`` and are selected by configuration. Imports of the
concrete providers happen *inside* the factory functions to keep the package
free of import cycles with ``app.services.ingestion``.
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
_RERANKERS: dict[str, type] = {}


def get_document_processor(settings: Settings) -> DocumentProcessor:
    from app.services.ingestion.processor import FileDocumentProcessor

    return FileDocumentProcessor()


def get_embedding_service(settings: Settings) -> EmbeddingService:
    from app.services.ingestion.embeddings import (
        FastEmbedEmbeddingProvider,
        HashingEmbeddingProvider,
    )

    provider = settings.embedding_provider.strip().lower()
    if provider == "hashing":
        return HashingEmbeddingProvider(dimension=settings.embedding_dim)
    if provider == "fastembed":
        return FastEmbedEmbeddingProvider(
            model=settings.embedding_model, dimension=settings.embedding_dim
        )
    raise ServiceNotConfiguredError(
        "SERVICE_NOT_CONFIGURED",
        f"Embedding provider '{settings.embedding_provider}' is unknown. "
        "Set EMBEDDING_PROVIDER to 'hashing' or 'fastembed'.",
    )


def get_vector_store(settings: Settings) -> VectorStore:
    """Build the configured vector store (raises when QDRANT_URL is empty)."""
    if not settings.qdrant_url:
        raise ServiceNotConfiguredError("SERVICE_NOT_CONFIGURED", "QDRANT_URL is not configured.")
    from app.services.ingestion.vector_store import QdrantVectorStore

    return QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection=settings.qdrant_collection,
    )


def build_vector_store(settings: Settings) -> VectorStore:
    """Startup variant: never raises.

    Returns an :class:`UnconfiguredVectorStore` when QDRANT_URL is empty so
    the app still boots; uploads then fail cleanly with SERVICE_NOT_CONFIGURED.
    """
    try:
        return get_vector_store(settings)
    except ServiceNotConfiguredError:
        from app.services.ingestion.vector_store import UnconfiguredVectorStore

        return UnconfiguredVectorStore()


def get_retriever(
    settings: Settings, *, db, vector_store: VectorStore | None = None
) -> Retriever:
    """Build the tenant-scoped retriever from configured providers.

    ``vector_store`` should be the app's shared instance (``app.state``) so
    embedded/in-memory stores are reused; when omitted the store is built from
    settings (raises SERVICE_NOT_CONFIGURED if QDRANT_URL is empty). The
    configured reranker is resolved here through :func:`get_reranker` — an
    unknown ``RERANKER_PROVIDER`` raises SERVICE_NOT_CONFIGURED (501) with no
    fallback to another provider.
    """
    from app.services.rag.retriever import TenantScopedRetriever

    store = vector_store if vector_store is not None else get_vector_store(settings)
    return TenantScopedRetriever(
        db=db,
        embedder=get_embedding_service(settings),
        vector_store=store,
        reranker=get_reranker(settings),
        rerank_top_k=settings.reranker_top_k,
        rerank_max_candidates=settings.reranker_max_candidates,
    )


def get_reranker(settings: Settings) -> Reranker:
    """Build the configured reranker.

    Importing the provider module self-registers it in ``_RERANKERS``. The
    provider name follows ``RERANKER_PROVIDER`` once configuration lands;
    until then the offline ``heuristic`` provider is the default, and any
    provider without an implementation keeps raising SERVICE_NOT_CONFIGURED.
    """
    from app.services.rag import reranker

    name = getattr(settings, "reranker_provider", None) or reranker.PROVIDER_NAME
    provider = _RERANKERS.get(str(name).strip().lower())
    if provider is None:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            f"Reranker provider '{name}' has no implementation yet.",
        )
    return provider()


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
    "build_vector_store",
    "get_document_processor",
    "get_embedding_service",
    "get_llm_provider",
    "get_reranker",
    "get_retriever",
    "get_vector_store",
]
