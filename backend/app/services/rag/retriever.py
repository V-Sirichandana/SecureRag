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

``retrieve_lexical()`` (milestone 3) mirrors the same authorization contract
for keyword candidates — validate → resolve role → tenant-fenced lexical
candidate generation → CURRENT permission filter → reranker — while the
``retrieve()`` flow above stays vector-only.

Hybrid flow (milestone 4, ``RETRIEVAL_MODE=hybrid`` — server-side
configuration, never client-selectable)::

    query → validate → resolve role (DB)
          → vector candidates (server tenant fence)
          + lexical candidates (server tenant fence)
          → deduplicate by chunk_id
          → ONE CURRENT permission check over the union
          → recompute source ranks over the AUTHORIZED set only
          → RRF fusion over AUTHORIZED candidates only
          → hard candidate cap → existing reranker
          → reranker output ∩ authorized pool → final top-k

Vector mode keeps the flow above byte-identical: ``score`` is the original
vector similarity. In hybrid mode ``score`` becomes the fused Reciprocal
Rank Fusion score (``RRF_K = 60``); raw vector/lexical scores and source
ranks stay internal to this module and are never exposed through the API.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, replace
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

# Reciprocal Rank Fusion constant (milestone 4): contribution = 1 / (60 + rank)
RRF_K = 60


@dataclass
class _FusedCandidate:
    """Internal hybrid candidate — never exposed outside this module.

    Holds the carrier :class:`RetrievedChunk` plus the PRIVATE per-source
    ranks and raw scores captured at deduplication time. ``chunk.score`` is
    rewritten to ``fused_score`` only on a copy when hybrid results are
    produced; the raw ``vector_score`` / ``lexical_score`` are kept purely
    for provenance and never reach the API.
    """

    chunk: RetrievedChunk
    vector_rank: int | None = None
    lexical_rank: int | None = None
    vector_score: float | None = None
    lexical_score: float | None = None
    fused_score: float = 0.0


def _union_candidates(
    vector_results: list[RetrievedChunk],
    lexical_results: list[RetrievedChunk],
) -> list[_FusedCandidate]:
    """Deduplicate both sources by ``chunk_id``, retaining private source order.

    The vector-sourced chunk is the carrier when a chunk appears in both
    sources (its raw similarity is preserved in ``vector_score``);
    lexical-only chunks carry their lexical ``RetrievedChunk``. The stored
    ranks are 1-based FETCH positions — they only encode relative source
    order. Before any RRF fusion they must be renumbered over the
    authorized set (:func:`_recompute_source_ranks`) so hidden candidates
    can never influence a visible candidate's score.
    """
    union: dict[str, _FusedCandidate] = {}
    for rank, chunk in enumerate(vector_results, start=1):
        # A well-behaved store returns each chunk once, but if a provider ever
        # duplicates an id, keep its FIRST (best) rank instead of letting a
        # later duplicate overwrite it.
        if chunk.chunk_id in union:
            continue
        union[chunk.chunk_id] = _FusedCandidate(
            chunk=chunk, vector_rank=rank, vector_score=chunk.score
        )
    for rank, chunk in enumerate(lexical_results, start=1):
        existing = union.get(chunk.chunk_id)
        if existing is None:
            union[chunk.chunk_id] = _FusedCandidate(
                chunk=chunk, lexical_rank=rank, lexical_score=chunk.score
            )
        elif existing.lexical_rank is None:
            # Cross-source duplicate: attach lexical provenance to the vector
            # carrier. If the lexical source itself repeats an id, first wins.
            existing.lexical_rank = rank
            existing.lexical_score = chunk.score
    return list(union.values())


def _recompute_source_ranks(candidates: list[_FusedCandidate]) -> list[_FusedCandidate]:
    """Renumber each source's ranks densely over the AUTHORIZED candidates only.

    Called between the single authorization check and RRF fusion so the
    fused score depends only on what the caller is allowed to see: a hidden
    candidate removed by authorization never shifts a visible candidate's
    rank (visible B behind hidden X scores as authorized rank 2, not fetch
    rank 3), which closes the rank side-channel. Relative source order —
    the original fetch ordering — is preserved; candidates absent from a
    source keep ``None``. Returns new instances; inputs are never mutated.
    """
    vector_order = sorted(
        (candidate for candidate in candidates if candidate.vector_rank is not None),
        key=lambda candidate: candidate.vector_rank,
    )
    lexical_order = sorted(
        (candidate for candidate in candidates if candidate.lexical_rank is not None),
        key=lambda candidate: candidate.lexical_rank,
    )
    vector_rank = {
        candidate.chunk.chunk_id: rank for rank, candidate in enumerate(vector_order, start=1)
    }
    lexical_rank = {
        candidate.chunk.chunk_id: rank for rank, candidate in enumerate(lexical_order, start=1)
    }
    return [
        replace(
            candidate,
            vector_rank=vector_rank.get(candidate.chunk.chunk_id),
            lexical_rank=lexical_rank.get(candidate.chunk.chunk_id),
        )
        for candidate in candidates
    ]


def _rrf_fuse(candidates: list[_FusedCandidate]) -> list[_FusedCandidate]:
    """Reciprocal Rank Fusion from the candidates' per-source ranks.

    ``fused_score = Σ 1 / (RRF_K + rank)`` across the sources where the
    candidate appears; raw vector/lexical scores never enter the formula.
    In the hybrid pipeline the ranks are authorization-relative (see
    :func:`_recompute_source_ranks`), so the score reflects only the
    candidates the caller may see. Ordering is fully deterministic: fused
    score DESC, then vector rank ASC (missing = +inf), then lexical rank
    ASC (missing = +inf), then ``chunk_id`` ASC. Returns new instances —
    inputs are never mutated.
    """
    fused: list[_FusedCandidate] = []
    for candidate in candidates:
        score = 0.0
        if candidate.vector_rank is not None:
            score += 1.0 / (RRF_K + candidate.vector_rank)
        if candidate.lexical_rank is not None:
            score += 1.0 / (RRF_K + candidate.lexical_rank)
        fused.append(replace(candidate, fused_score=score))
    fused.sort(
        key=lambda candidate: (
            -candidate.fused_score,
            candidate.vector_rank
            if candidate.vector_rank is not None
            else math.inf,
            candidate.lexical_rank
            if candidate.lexical_rank is not None
            else math.inf,
            candidate.chunk.chunk_id,
        )
    )
    return fused


class TenantScopedRetriever:
    """Implements the :class:`Retriever` protocol.

    Depends only on the embedding service, the vector store, a database
    session and — optionally — a reranker. ``tenant_id`` / ``user_id`` are
    passed in by the caller from the authenticated principal. The reranker is
    a pure re-ordering step applied AFTER authorization; it never sees and
    never influences which documents the caller is allowed to read. An
    optional lexical index is injected and exposed through the separate
    :meth:`retrieve_lexical` candidate path (milestone 3); the public
    ``retrieve()`` method stays vector-only until the hybrid merge.

    ``retrieval_mode`` (milestone 4) is server-side configuration:
    ``"vector"`` (default) keeps ``retrieve()`` exactly as before,
    ``"hybrid"`` adds the fused candidate path. An unknown internal mode is
    rejected at construction — it never silently becomes hybrid.
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
        retrieval_mode: str = "vector",
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker
        self.rerank_top_k = rerank_top_k
        self.rerank_max_candidates = rerank_max_candidates
        # only the separate retrieve_lexical() path reads this; retrieve()
        # stays vector-only until the hybrid merge
        self.lexical_index = lexical_index
        mode = (retrieval_mode or "").strip().lower()
        if mode not in ("vector", "hybrid"):
            raise ValueError(
                f"retrieval_mode must be 'vector' or 'hybrid', got {retrieval_mode!r}"
            )
        self.retrieval_mode = mode

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
        if self.retrieval_mode == "hybrid":
            return await self._hybrid_search(
                query=text,
                tenant_id=tenant_id,
                user_id=user_id,
                role=role,
                collection_ids=collection_ids,
                top_k=top_k,
            )
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

    async def retrieve_lexical(
        self,
        *,
        query: str,
        tenant_id: str,
        user_id: str,
        collection_ids: list[str] | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[RetrievedChunk]:
        """Lexical (keyword) candidate path — milestone 3.

        Deliberately separate from :meth:`retrieve`, which stays byte-identical
        vector-only. Same authorization contract, same order of operations:
        validate → resolve the role from the database → tenant-fenced lexical
        candidate generation (a candidate generator, NOT an authorization
        layer) → CURRENT document permissions as the only visibility truth →
        reranker over authorized chunks only. Returns ``[]`` when no lexical
        index is wired.
        """
        text = self._validate(query, top_k)
        role = await self._resolve_role(tenant_id=tenant_id, user_id=user_id)
        return await self._lexical_search(
            query=text,
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

    async def _hybrid_search(
        self,
        *,
        query: str,
        tenant_id: str,
        user_id: str,
        role: Role,
        collection_ids: list[str] | None,
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Vector + lexical candidates → ONE permission check → RRF → rerank.

        Milestone 4 security boundary, in order: an explicitly configured
        hybrid mode requires a real lexical index (501 otherwise — never a
        silent vector-only fallback) → embed ONCE (vector retrieval only;
        lexical receives the validated query text) → both sources fetch the
        same bounded ``_initial_fetch(top_k)`` size (≤ ``MAX_CANDIDATES``),
        each applying its OWN server-derived tenant fence → deduplicate by
        ``chunk_id`` → :meth:`_visible_document_ids` EXACTLY once over the
        union → RRF fusion over AUTHORIZED candidates only → the existing
        reranker pool cap → the existing reranker.

        Any source failure propagates with the existing error mapping (no
        partial hybrid results); a source returning ``[]`` is successful
        retrieval, not a failure.
        """
        self._require_lexical_index()
        vector = await self._embed(query)  # exactly once, vector path only
        fetch = self._initial_fetch(top_k)
        extra_filter: dict[str, Any] | None = (
            {"collection_id": collection_ids} if collection_ids else None
        )
        vector_candidates = await self._vector_search(
            vector=vector, tenant_id=tenant_id, fetch=fetch, extra_filter=extra_filter
        )
        lexical_candidates = await self._lexical_candidates(
            query=query, tenant_id=tenant_id, collection_ids=collection_ids, fetch=fetch
        )

        # deduplicate BEFORE authorization: one choke point over the union
        union = _union_candidates(vector_candidates, lexical_candidates)
        visible = await self._visible_document_ids(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            candidates=[candidate.chunk for candidate in union],
        )
        authorized = [
            candidate for candidate in union if candidate.chunk.document_id in visible
        ]
        # M-2: ranks are recomputed OVER THE AUTHORIZED SET before fusion, so
        # a hidden candidate can never influence a visible candidate's fused
        # score (no rank side-channel). ONLY authorized candidates are fused —
        # unauthorized chunks never receive a fused score, never enter the
        # ordering, never reach the reranker
        fused = _rrf_fuse(_recompute_source_ranks(authorized))
        chunks = [replace(candidate.chunk, score=candidate.fused_score) for candidate in fused]
        # the existing _rerank applies _rerank_pool_limit (40) and top_k;
        # rerank_score behavior is unchanged
        return await self._rerank(query=query, chunks=chunks, top_k=top_k)

    def _require_lexical_index(self) -> None:
        """Hybrid mode must never silently degrade to vector-only retrieval."""
        from app.services.rag.lexical import NullLexicalIndex  # cycle guard

        if self.lexical_index is None or isinstance(self.lexical_index, NullLexicalIndex):
            raise AppError(
                "SERVICE_NOT_CONFIGURED",
                "Hybrid retrieval requires a configured lexical index.",
            )

    async def _lexical_search(
        self,
        *,
        query: str,
        tenant_id: str,
        user_id: str,
        role: Role,
        collection_ids: list[str] | None,
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Lexical candidates → CURRENT permission filter → rerank.

        Single-shot (no expansion rounds): the fetch is bounded by the same
        ``_initial_fetch`` sizing as the vector path (never above
        ``MAX_CANDIDATES``, hence never above ``MAX_TOP_K`` either). The
        lexical index only fences by tenant inside SQL — visibility is
        decided exclusively here, from the CURRENT database permissions,
        exactly as in the vector path.
        """
        if self.lexical_index is None:
            return []
        fetch = self._initial_fetch(top_k)
        candidates = await self._lexical_candidates(
            query=query,
            tenant_id=tenant_id,
            collection_ids=collection_ids,
            fetch=fetch,
        )

        visible = await self._visible_document_ids(
            tenant_id=tenant_id, user_id=user_id, role=role, candidates=candidates
        )
        authorized = [chunk for chunk in candidates if chunk.document_id in visible]
        # ONLY authorized chunks are handed to the reranker
        return await self._rerank(query=query, chunks=authorized, top_k=top_k)

    async def _lexical_candidates(
        self,
        *,
        query: str,
        tenant_id: str,
        collection_ids: list[str] | None,
        fetch: int,
    ) -> list[RetrievedChunk]:
        """Source-level lexical candidate generation — no authorization, no rerank.

        The single seam both the lexical and hybrid paths use, so the error
        mapping can never drift between them: domain errors keep their
        status, unexpected storage failures become SERVICE_UNAVAILABLE (503)
        without leaking internals.
        """
        if self.lexical_index is None:
            return []
        try:
            return await self.lexical_index.search(
                query=query,
                tenant_id=tenant_id,
                collection_ids=collection_ids,
                top_k=fetch,
            )
        except AppError:
            raise  # SERVICE_NOT_CONFIGURED / VALIDATION keep their status
        except Exception as exc:  # noqa: BLE001 - never leak storage internals
            logger.exception("Lexical search failed")
            raise AppError("SERVICE_UNAVAILABLE") from exc

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
        """Effective reranker pool cap: config may LOWER it, never raise it.

        ``RERANKER_MAX_CANDIDATES`` is runtime configuration, so it is
        clamped against the hard server-side maximum (``MAX_CANDIDATES``) —
        no configuration can grow the pool above 40. Non-positive values
        (only reachable through direct construction; Settings enforces
        ``ge=1``) stay floored at 1, preserving the existing convention.
        """
        if self.rerank_max_candidates is None:
            return MAX_CANDIDATES
        return min(max(self.rerank_max_candidates, 1), MAX_CANDIDATES)

    async def _rerank(
        self, *, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        """Re-order already-authorized chunks and cut to the final result count.

        ``chunks`` arrive exclusively from the tenant + permission filter
        above; the reranker is never consulted for visibility. Its output is
        then intersected with the authorized pool it was given
        (:meth:`_constrain_to_pool`) — a reranker may REORDER authorized
        candidates but can never introduce one. The final count never
        exceeds what the caller requested, and the vector ``score`` of every
        chunk survives untouched (``rerank_score`` carries the new one).
        """
        if self.reranker is None:
            return chunks[:top_k]
        pool = chunks[: self._rerank_pool_limit]
        final_k = min(top_k, self.rerank_top_k)
        try:
            reranked = await self.reranker.rerank(query=query, chunks=pool, top_k=final_k)
            # bounded by min(top_k, rerank_top_k) even if the provider over-returns
            return self._constrain_to_pool(pool, reranked)[:final_k]
        except AppError:
            raise  # SERVICE_NOT_CONFIGURED / VALIDATION keep their status
        except Exception as exc:  # noqa: BLE001 - never leak reranker internals
            logger.exception("Reranking failed")
            raise AppError("SERVICE_UNAVAILABLE") from exc

    @staticmethod
    def _constrain_to_pool(
        pool: list[RetrievedChunk], reranked: object
    ) -> list[RetrievedChunk]:
        """Reranker-output authorization boundary (integrity check only).

        Keeps only reranker results whose ``chunk_id`` belongs to the
        authorized pool the reranker was handed, in the reranker's order —
        first occurrence wins, duplicates and unknown/malformed entries are
        dropped, and results are never refilled. Payload fields come from
        the pool copy (only ``rerank_score`` is taken from the output), so
        even a rogue provider cannot smuggle altered content past the
        authorized set. No second database query happens here: this checks
        identity against an already-authorized pool.
        """
        if not isinstance(reranked, list):
            raise AppError(
                "SERVICE_UNAVAILABLE", "The reranker returned an unexpected result."
            )
        authorized: dict[str, RetrievedChunk] = {}
        for chunk in pool:
            authorized.setdefault(chunk.chunk_id, chunk)
        final: list[RetrievedChunk] = []
        seen: set[str] = set()
        for candidate in reranked:
            chunk_id = getattr(candidate, "chunk_id", None)
            if not isinstance(chunk_id, str) or chunk_id not in authorized:
                continue  # unknown / malformed entry — never introduced
            if chunk_id in seen:
                continue  # duplicate — first occurrence wins
            seen.add(chunk_id)
            source = authorized[chunk_id]
            final.append(
                replace(source, rerank_score=getattr(candidate, "rerank_score", None))
            )
        return final

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
