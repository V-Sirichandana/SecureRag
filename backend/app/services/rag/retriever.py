"""Tenant-scoped, permission-aware retrieval.

Flow::

    query → validate → resolve role (DB) → embed (once)
          → Qdrant search WITH server-derived tenant filter
          → candidate document ids
          → CURRENT document permissions from the database
          → authorized chunks only (bounded candidate expansion)
          → reranker re-scores AUTHORIZED chunks only → final top-k

The database is the single source of truth for authorization. Payload hints
stored at ingest time (``access`` / ``classification`` / ``created_by``) are
never consulted — they can be stale after role, membership or permission
changes.

The reranker never participates in authorization: it only ever receives
chunks that already passed the tenant filter and the CURRENT permission
check, and it cannot widen the result set beyond what those checks allowed.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, AuthorizationError
from app.core.permissions import Role, role_at_least
from app.models import Document
from app.repositories import DocumentRepository, UserRepository
from app.services.rag.base import (
    EmbeddingService,
    LexicalIndex,
    Reranker,
    RetrievedChunk,
    VectorStore,
)

logger = logging.getLogger("securerag.retrieval")

MAX_QUERY_LENGTH = 1000
MAX_TOP_K = 50
DEFAULT_TOP_K = 10

# bounded candidate expansion — never loop unbounded against the vector store
MAX_CANDIDATES = 40
MAX_EXPANSION_ROUNDS = 3


class TenantScopedRetriever:
    """Implements the :class:`Retriever` protocol.

    Depends only on the embedding service, the vector store, a database
    session and — optionally — a reranker. ``tenant_id`` / ``user_id`` are
    passed in by the caller from the authenticated principal. The reranker is
    a pure re-ordering step applied AFTER authorization; it never sees and
    never influences which documents the caller is allowed to read. An
    optional lexical index may be injected but is not consulted yet —
    retrieval stays vector-only until the hybrid merge.
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        embedder: EmbeddingService,
        vector_store: VectorStore,
        reranker: Reranker | None = None,
        rerank_top_k: int = DEFAULT_TOP_K,
        rerank_max_candidates: int | None = None,
        lexical_index: LexicalIndex | None = None,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker
        self.rerank_top_k = rerank_top_k
        self.rerank_max_candidates = rerank_max_candidates
        # dependency-injection seam only: deliberately never read here, so
        # lexical search cannot influence results before the hybrid merge
        self.lexical_index = lexical_index

    async def retrieve(
        self,
        *,
        query: str,
        tenant_id: str,
        user_id: str,
        collection_ids: list[str] | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[RetrievedChunk]:
        text = self._validate(query, top_k)
        role = await self._resolve_role(tenant_id=tenant_id, user_id=user_id)
        vector = await self._embed(text)
        return await self._search(
            query=text,
            vector=vector,
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            collection_ids=collection_ids,
            top_k=top_k,
        )

    # ------------------------------------------------------------- validation
    @staticmethod
    def _validate(query: str, top_k: int) -> str:
        text = (query or "").strip()
        if not text:
            raise AppError("VALIDATION_ERROR", "Search query must not be empty.")
        if len(text) > MAX_QUERY_LENGTH:
            raise AppError(
                "VALIDATION_ERROR",
                f"Search query must be at most {MAX_QUERY_LENGTH} characters.",
            )
        if not 1 <= top_k <= MAX_TOP_K:
            raise AppError(
                "VALIDATION_ERROR",
                f"top_k must be between 1 and {MAX_TOP_K}.",
            )
        return text

    # ------------------------------------------------------- identity (server)
    async def _resolve_role(self, *, tenant_id: str, user_id: str) -> Role:
        """Look the membership up in the DB — client input is never trusted."""
        try:
            tenant_uuid = uuid.UUID(tenant_id)
            user_uuid = uuid.UUID(user_id)
        except ValueError as exc:
            raise AuthorizationError(
                "TENANT_ACCESS_DENIED", "Invalid tenant or user context."
            ) from exc
        membership = await UserRepository(self.db).membership(user_uuid, tenant_uuid)
        if membership is None:
            # defense in depth: the caller must actually belong to this tenant
            raise AuthorizationError(
                "TENANT_ACCESS_DENIED",
                "You are not a member of the requested organization.",
            )
        return membership.role

    # ------------------------------------------------------------- embedding
    async def _embed(self, text: str) -> list[float]:
        try:
            return await self.embedder.embed_query(text)
        except AppError:
            raise  # configuration errors keep their 501/4xx status
        except Exception as exc:  # noqa: BLE001 - never leak provider internals
            logger.exception("Query embedding failed")
            raise AppError("SERVICE_UNAVAILABLE") from exc

    # ------------------------------------------------------- search + filter
    async def _search(
        self,
        *,
        query: str,
        vector: list[float],
        tenant_id: str,
        user_id: str,
        role: Role,
        collection_ids: list[str] | None,
        top_k: int,
    ) -> list[RetrievedChunk]:
        extra_filter: dict[str, Any] | None = (
            {"collection_id": collection_ids} if collection_ids else None
        )
        fetch = self._initial_fetch(top_k)
        authorized: list[RetrievedChunk] = []

        for _ in range(MAX_EXPANSION_ROUNDS):
            candidates = await self._vector_search(
                vector=vector, tenant_id=tenant_id, fetch=fetch, extra_filter=extra_filter
            )
            visible = await self._visible_document_ids(
                tenant_id=tenant_id, user_id=user_id, role=role, candidates=candidates
            )
            authorized = [chunk for chunk in candidates if chunk.document_id in visible]

            # stop when: enough authorized results, the store is exhausted,
            # or we already hit the candidate cap
            if (
                len(authorized) >= top_k
                or len(candidates) < fetch
                or fetch >= MAX_CANDIDATES
            ):
                break
            fetch = min(fetch * 2, MAX_CANDIDATES)

        # ONLY authorized chunks are handed to the reranker
        return await self._rerank(query=query, chunks=authorized, top_k=top_k)

    def _initial_fetch(self, top_k: int) -> int:
        """Vector candidate request size for one round.

        With a reranker the target is ``min(top_k * 3, RERANKER_MAX_CANDIDATES)``
        (never below the requested ``top_k``, never above the hard
        ``MAX_CANDIDATES`` safety cap). Without one the legacy expansion
        sizing is kept unchanged.
        """
        if self.reranker is None:
            return min(max(top_k * 3, 12), MAX_CANDIDATES)
        target = min(top_k * 3, self._rerank_pool_limit)
        return min(max(target, top_k), MAX_CANDIDATES)

    @property
    def _rerank_pool_limit(self) -> int:
        if self.rerank_max_candidates is None:
            return MAX_CANDIDATES
        return max(self.rerank_max_candidates, 1)

    async def _rerank(
        self, *, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        """Re-order already-authorized chunks and cut to the final result count.

        ``chunks`` arrive exclusively from the tenant + permission filter
        above; the reranker is never consulted for visibility. The final count
        never exceeds what the caller requested, and the vector ``score`` of
        every chunk survives untouched (``rerank_score`` carries the new one).
        """
        if self.reranker is None:
            return chunks[:top_k]
        pool = chunks[: self._rerank_pool_limit]
        final_k = min(top_k, self.rerank_top_k)
        try:
            return await self.reranker.rerank(query=query, chunks=pool, top_k=final_k)
        except AppError:
            raise  # SERVICE_NOT_CONFIGURED / VALIDATION keep their status
        except Exception as exc:  # noqa: BLE001 - never leak reranker internals
            logger.exception("Reranking failed")
            raise AppError("SERVICE_UNAVAILABLE") from exc

    async def _vector_search(
        self,
        *,
        vector: list[float],
        tenant_id: str,
        fetch: int,
        extra_filter: dict[str, Any] | None,
    ) -> list[RetrievedChunk]:
        try:
            # tenant_id is server-derived here and the store ALWAYS applies it
            return await self.vector_store.search(
                vector=vector,
                tenant_id=tenant_id,
                top_k=fetch,
                extra_filter=extra_filter,
            )
        except AppError:
            raise  # SERVICE_NOT_CONFIGURED keeps its 501
        except Exception as exc:  # noqa: BLE001 - never leak vector store internals
            logger.exception("Vector search failed")
            raise AppError("SERVICE_UNAVAILABLE") from exc

    async def _visible_document_ids(
        self,
        *,
        tenant_id: str,
        user_id: str,
        role: Role,
        candidates: list[RetrievedChunk],
    ) -> set[str]:
        """Batched CURRENT permission check against the database.

        Uses the existing ``DocumentRepository.visibility_clause`` — the exact
        rule backing ``DocumentService._can_view`` for non-admins (own
        documents, explicit user/role grants, org-wide grants). ADMIN+ sees
        every document in its tenant, mirroring ``_can_view``.
        One query per round, never one per chunk.
        """
        document_ids: list[uuid.UUID] = []
        for chunk in candidates:
            if not chunk.document_id:
                continue
            try:
                document_ids.append(uuid.UUID(chunk.document_id))
            except ValueError:
                continue  # malformed payload id — treat as not visible
        if not document_ids:
            return set()

        query = select(Document.id).where(
            Document.tenant_id == uuid.UUID(tenant_id),
            Document.id.in_(document_ids),
        )
        if not role_at_least(role, Role.ADMIN):
            query = query.where(
                DocumentRepository.visibility_clause(uuid.UUID(user_id), role.value)
            )
        rows = (await self.db.execute(query)).scalars()
        return {str(row) for row in rows}


__all__ = ["MAX_QUERY_LENGTH", "MAX_TOP_K", "TenantScopedRetriever"]
