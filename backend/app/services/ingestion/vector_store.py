"""Qdrant vector store with mandatory server-side tenant filtering.

One collection is shared by every tenant; isolation is enforced by a
``tenant_id`` filter that the *server* builds from the authenticated
principal. Callers cannot override it — see :func:`build_tenant_filter`.

``QDRANT_URL=:memory:`` selects an embedded in-process instance (tests and
local development without Docker). Real deployments point QDRANT_URL at a
Docker/managed Qdrant server.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from qdrant_client import QdrantClient, models

from app.core.exceptions import AppError, ServiceNotConfiguredError
from app.services.rag.base import RetrievedChunk, VectorStore

MEMORY_URL = ":memory:"
logger = logging.getLogger("securerag.vector_store")


class VectorDimensionMismatchError(AppError):
    """Existing collection cannot accept vectors of the configured width.

    This is a read-only guard: no collection is recreated, resized or deleted.
    """

    def __init__(self) -> None:
        super().__init__(
            "VECTOR_DIMENSION_MISMATCH",
            "The vector collection was created with a different embedding dimension. "
            "Refusing to write into it; use a matching EMBEDDING_* configuration or "
            "a new collection. Existing vectors were not modified.",
            status_code=503,
        )


def _safe_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Payload fields safe to hand to authorized callers.

    Internal authorization hints (``created_by``, ``access``) and anything not
    explicitly listed never leave the vector store.
    """
    return {
        "tenant_id": str(payload.get("tenant_id", "")),
        "document_name": str(payload.get("name", "")),
        "classification": str(payload.get("classification", "")),
        "chunk_index": int(payload.get("chunk_index", 0)),
    }


def build_tenant_filter(
    tenant_id: str,
    *,
    collection_id: str | None = None,
    document_ids: list[str] | None = None,
    extra_filter: dict[str, Any] | None = None,
) -> models.Filter:
    """Build the query filter. ``tenant_id`` ALWAYS wins.

    Any caller-supplied ``extra_filter`` may add constraints (classification,
    access, ...) but a caller-supplied ``tenant_id`` entry is discarded — a
    foreign tenant id can never widen or redirect the search.
    """
    must: list[models.Condition] = [
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value=str(tenant_id)))
    ]
    if collection_id:
        must.append(
            models.FieldCondition(
                key="collection_id", match=models.MatchValue(value=str(collection_id))
            )
        )
    if document_ids:
        must.append(
            models.FieldCondition(
                key="document_id", match=models.MatchAny(any=[str(d) for d in document_ids])
            )
        )
    for key, value in (extra_filter or {}).items():
        if key == "tenant_id":
            continue  # never allow a caller-supplied tenant to bypass authz
        if isinstance(value, (list, tuple, set)):
            must.append(
                models.FieldCondition(key=key, match=models.MatchAny(any=[str(v) for v in value]))
            )
        else:
            must.append(models.FieldCondition(key=key, match=models.MatchValue(value=str(value))))
    return models.Filter(must=must)


class QdrantVectorStore:
    """Implements the :class:`VectorStore` protocol on top of Qdrant."""

    def __init__(self, *, url: str, api_key: str = "", collection: str = "securerag") -> None:
        if not url:
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED", "QDRANT_URL is not configured."
            )
        self._collection = collection or "securerag"
        if url == MEMORY_URL:
            self._client = QdrantClient(location=MEMORY_URL)
        else:
            self._client = QdrantClient(url=url, api_key=api_key or None)
        self._ensured: set[int] = set()
        self._existing_checked = False

    @property
    def collection_name(self) -> str:
        """Read-only collection binding (used by migration tooling)."""
        return self._collection

    # ------------------------------------------------------------- indexing
    async def upsert_chunks(
        self,
        *,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        vector_size: int,
    ) -> None:
        if len(vectors) != len(payloads):
            raise ValueError("vectors and payloads must have the same length")
        if not vectors:
            return
        await asyncio.to_thread(self._ensure_collection, vector_size)
        points = [
            models.PointStruct(
                id=payload["chunk_id"],
                vector=vector,
                payload=payload,
            )
            for vector, payload in zip(vectors, payloads, strict=True)
        ]
        await asyncio.to_thread(
            lambda: self._client.upsert(collection_name=self._collection, points=points, wait=True)
        )

    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        """Delete one document's vectors — scoped to its own tenant."""
        if not await asyncio.to_thread(self._collection_exists):
            return
        delete_filter = build_tenant_filter(tenant_id, document_ids=[document_id])
        await asyncio.to_thread(
            lambda: self._client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(filter=delete_filter),
                wait=True,
            )
        )

    # -------------------------------------------------------------- searching
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
        if not await asyncio.to_thread(self._collection_exists):
            return []  # nothing indexed yet
        query_filter = build_tenant_filter(
            tenant_id,
            collection_id=collection_id,
            document_ids=document_ids,
            extra_filter=extra_filter,
        )
        response = await asyncio.to_thread(
            lambda: self._client.query_points(
                collection_name=self._collection,
                query=vector,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
        )
        results: list[RetrievedChunk] = []
        for point in response.points:
            payload = point.payload or {}
            text = str(payload.get("text", ""))
            results.append(
                RetrievedChunk(
                    text=text,
                    score=float(point.score),
                    document_id=str(payload.get("document_id", "")),
                    collection_id=str(payload.get("collection_id") or "") or None,
                    page_number=int(payload.get("page", 1)),
                    quote=text[:200],
                    chunk_id=str(payload.get("chunk_id", "")),
                    filename=str(payload.get("filename", "")),
                    metadata=_safe_metadata(payload),
                )
            )
        return results

    # -------------------------------------------------------------- internals
    def _ensure_collection(self, vector_size: int) -> None:
        if vector_size in self._ensured:
            return
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=models.VectorParams(
                    size=vector_size, distance=models.Distance.COSINE
                ),
            )
        else:
            existing_size = self._collection_vector_size()
            if existing_size is not None and existing_size != vector_size:
                logger.error(
                    "Qdrant collection %s has vector dimension %s but the active "
                    "embedder produces %s; refusing to write",
                    self._collection,
                    existing_size,
                    vector_size,
                )
                raise VectorDimensionMismatchError()
        self._ensured.add(vector_size)
        self._existing_checked = True

    def _collection_vector_size(self) -> int | None:
        """Read the existing collection width without modifying it."""
        info = self._client.get_collection(self._collection)
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):
            # Named-vector collections are not created by this application;
            # never guess which vector a write should target.
            return None
        size = getattr(vectors, "size", None)
        return int(size) if size is not None else None

    def _collection_exists(self) -> bool:
        if self._existing_checked:
            return True
        exists = self._client.collection_exists(self._collection)
        if exists:
            self._existing_checked = True
        return exists

    def check_health(self) -> None:
        """Read-only connectivity check used by the readiness probe."""
        self._client.get_collections()


class UnconfiguredVectorStore:
    """Stand-in used when QDRANT_URL is empty.

    Writes/queries report SERVICE_NOT_CONFIGURED (501); deletes are a no-op
    because an environment without a vector backend has no vectors to leak.
    """

    async def upsert_chunks(
        self,
        *,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        vector_size: int,
    ) -> None:
        raise ServiceNotConfiguredError("SERVICE_NOT_CONFIGURED", "QDRANT_URL is not configured.")

    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        return None

    def check_health(self) -> None:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED", "QDRANT_URL is not configured."
        )

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
        raise ServiceNotConfiguredError("SERVICE_NOT_CONFIGURED", "QDRANT_URL is not configured.")


__all__ = [
    "MEMORY_URL",
    "QdrantVectorStore",
    "UnconfiguredVectorStore",
    "VectorStore",
    "build_tenant_filter",
]
