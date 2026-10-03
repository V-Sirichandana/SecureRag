"""RAG service interfaces (preparation phase).

These protocols are the seams where the ingestion pipeline, vector store,
retriever, reranker and LLM provider plug in during the RAG phase. Nothing is
tied to a specific vendor: implementations register themselves against these
interfaces and are selected by configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ProcessedChunk:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    text: str
    score: float
    document_id: str
    collection_id: str | None = None
    page_number: int = 1
    quote: str = ""
    chunk_id: str = ""
    filename: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    rerank_score: float | None = None


@dataclass
class GenerationResult:
    content: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0
    token_count: int = 0


@runtime_checkable
class DocumentProcessor(Protocol):
    async def process(
        self, *, document_id: str, file_name: str, content: bytes
    ) -> list[ProcessedChunk]:
        """Parse raw file bytes into chunkable text with metadata."""
        ...


@runtime_checkable
class EmbeddingService(Protocol):
    @property
    def dimension(self) -> int:
        """Vector width produced by this provider (never hard-coded elsewhere)."""
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string with the same vector space."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    async def upsert_chunks(
        self,
        *,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        vector_size: int,
    ) -> None:
        """Index chunks. Each payload MUST carry tenant_id and chunk_id."""
        ...

    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        """Remove every vector belonging to one document inside one tenant."""
        ...

    async def search(
        self,
        *,
        vector: list[float],
        tenant_id: str,
        collection_id: str | None = None,
        document_ids: list[str] | None = None,
        top_k: int = 8,
        extra_filter: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Tenant-scoped similarity search.

        ``tenant_id`` comes from the authenticated principal and is always
        applied server-side; ``extra_filter`` can never override it.
        """
        ...


@runtime_checkable
class LexicalIndex(Protocol):
    """Tenant-scoped lexical (keyword) retrieval seam.

    The future BM25-style backend implements this protocol; until one is
    configured, the factory resolves the explicit no-op provider. Contracts
    mirror :class:`VectorStore`: ``tenant_id`` always comes from the
    authenticated principal and must be applied server-side, and ingestion
    replaces a document's records atomically so re-ingests never leave
    stale content searchable.
    """

    async def search(
        self,
        *,
        query: str,
        tenant_id: str,
        collection_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        """Tenant-scoped lexical search returning no more than ``top_k`` hits.

        ``tenant_id`` comes from the authenticated principal and is always
        applied server-side. Raw engine scores are implementation detail —
        callers merge by rank, never by raw score.
        """
        ...

    async def replace_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        payloads: list[dict[str, Any]],
    ) -> None:
        """Replace every lexical record of one document (idempotent re-ingest).

        ``payloads`` carries the same field names the ingestion pipeline
        already writes to the vector store (``chunk_id``, ``text``, ``page``,
        ``chunk_index``, ``filename``, ...) so both indexes stay aligned.
        """
        ...

    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        """Remove every lexical record belonging to one document inside one tenant."""
        ...


@runtime_checkable
class Retriever(Protocol):
    async def retrieve(
        self,
        *,
        query: str,
        tenant_id: str,
        user_id: str,
        collection_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        """Tenant-scoped, permission-checked similarity search.

        ``tenant_id`` / ``user_id`` come from the authenticated principal and
        are never client-supplied. The vector filter always includes
        ``tenant_id`` and every returned chunk is checked against the caller's
        CURRENT document view permissions in the database.
        """
        ...


@runtime_checkable
class Reranker(Protocol):
    async def rerank(
        self, *, query: str, chunks: list[RetrievedChunk], top_k: int = 5
    ) -> list[RetrievedChunk]:
        ...


@runtime_checkable
class LLMProvider(Protocol):
    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        context: list[RetrievedChunk],
        max_tokens: int = 1024,
    ) -> GenerationResult:
        """Produce a grounded answer with citations from retrieved context."""
        ...
