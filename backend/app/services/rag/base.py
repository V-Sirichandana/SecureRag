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
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(
        self,
        *,
        collection: str,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> None:
        ...

    async def search(
        self,
        *,
        collection: str,
        vector: list[float],
        top_k: int,
        filter: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        ...


@runtime_checkable
class Retriever(Protocol):
    async def retrieve(
        self,
        *,
        query: str,
        tenant_id: str,
        collection_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        """Tenant-scoped similarity search — the filter always includes tenant_id."""
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
