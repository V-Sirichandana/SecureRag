"""Document ingestion: processing, chunking, embeddings and vector indexing."""

from __future__ import annotations

from app.services.ingestion.chunker import Chunk, ChunkingService
from app.services.ingestion.embeddings import (
    FastEmbedEmbeddingProvider,
    HashingEmbeddingProvider,
)
from app.services.ingestion.pipeline import IngestionPipeline, IngestionResult
from app.services.ingestion.processor import FileDocumentProcessor
from app.services.ingestion.vector_store import (
    QdrantVectorStore,
    UnconfiguredVectorStore,
    build_tenant_filter,
)

__all__ = [
    "Chunk",
    "ChunkingService",
    "FastEmbedEmbeddingProvider",
    "FileDocumentProcessor",
    "HashingEmbeddingProvider",
    "IngestionPipeline",
    "IngestionResult",
    "QdrantVectorStore",
    "UnconfiguredVectorStore",
    "build_tenant_filter",
]
