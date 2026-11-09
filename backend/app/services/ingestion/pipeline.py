"""The ingestion pipeline: bytes → text → chunks → embeddings → indexes.

    upload → validate → extract → normalize → chunk → embed → payloads
           → lexical.replace_document → Qdrant delete → Qdrant upsert
                                   → document status updated by caller

The pipeline owns no database session and no status transition: it receives
the server-derived ``tenant_id`` and returns counts, while the calling
``DocumentService`` owns the document status transition (processing →
ready / failed) and the audit trail. Lexical rows are written through the
:class:`~app.services.rag.base.LexicalIndex` seam using the caller's own
session (flush-only), so the caller's commit/rollback decides whether they
become durable — a Qdrant failure after the lexical write is rolled back
together with any staged rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.exceptions import AppError
from app.services.ingestion.chunker import Chunk, ChunkingService
from app.services.ingestion.processor import FileDocumentProcessor
from app.services.rag.base import (
    DocumentProcessor,
    EmbeddingService,
    LexicalIndex,
    VectorStore,
)


@dataclass(frozen=True)
class IngestionResult:
    chunk_count: int
    page_count: int


class IngestionPipeline:
    def __init__(
        self,
        *,
        processor: DocumentProcessor,
        chunker: ChunkingService,
        embedder: EmbeddingService,
        vector_store: VectorStore,
        lexical_index: LexicalIndex,
    ) -> None:
        self.processor = processor
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store
        self.lexical_index = lexical_index

    @classmethod
    def build(
        cls, settings: Settings, vector_store: VectorStore, lexical_index: LexicalIndex
    ) -> IngestionPipeline:
        """Wire the pipeline from configuration (provider stays swappable)."""
        from app.services.rag import get_embedding_service  # local: avoid import cycle

        return cls(
            processor=FileDocumentProcessor(),
            chunker=ChunkingService(
                chunk_size=settings.chunk_size, overlap=settings.chunk_overlap
            ),
            embedder=get_embedding_service(settings),
            vector_store=vector_store,
            lexical_index=lexical_index,
        )

    # ------------------------------------------------------------------ runs
    async def ingest(
        self,
        *,
        tenant_id: str,
        document_id: str,
        collection_id: str | None,
        file_name: str,
        content: bytes,
        document_meta: dict[str, Any] | None = None,
    ) -> IngestionResult:
        """Index one document. ``tenant_id`` is server-derived, never client input."""
        segments = await self.processor.process(
            document_id=document_id, file_name=file_name, content=content
        )
        chunks = self.chunker.chunk(segments)
        if not chunks:
            raise AppError(
                "EMPTY_DOCUMENT",
                "No extractable text was found in the uploaded file.",
            )

        vectors = await self.embedder.embed_documents([chunk.text for chunk in chunks])
        payloads = [
            self._payload(
                chunk=chunk,
                tenant_id=tenant_id,
                document_id=document_id,
                collection_id=collection_id,
                file_name=file_name,
                document_meta=document_meta or {},
            )
            for chunk in chunks
        ]

        # lexical FIRST — a lexical failure aborts before any Qdrant mutation;
        # a later Qdrant failure is undone by the caller's rollback, which
        # also discards these flush-only lexical rows
        await self.lexical_index.replace_document(
            tenant_id=tenant_id, document_id=document_id, payloads=payloads
        )
        # replace any previous version of this document (idempotent re-ingest)
        await self.vector_store.delete_document(tenant_id=tenant_id, document_id=document_id)
        await self.vector_store.upsert_chunks(
            vectors=vectors, payloads=payloads, vector_size=self.embedder.dimension
        )

        return IngestionResult(
            chunk_count=len(chunks),
            page_count=max((chunk.page for chunk in chunks), default=1),
        )

    # -------------------------------------------------------------- internals
    @staticmethod
    def _payload(
        *,
        chunk: Chunk,
        tenant_id: str,
        document_id: str,
        collection_id: str | None,
        file_name: str,
        document_meta: dict[str, Any],
    ) -> dict[str, Any]:
        """Every vector carries the metadata secure retrieval needs.

        ``tenant_id`` here is passed by the service from the authenticated
        membership — the client can never inject or override it.
        """
        return {
            "chunk_id": chunk.chunk_id,
            "tenant_id": str(tenant_id),
            "document_id": str(document_id),
            "collection_id": str(collection_id) if collection_id else None,
            "chunk_index": chunk.index,
            "page": chunk.page,
            "filename": file_name,
            "text": chunk.text,
            **document_meta,
        }


__all__ = ["IngestionPipeline", "IngestionResult"]
