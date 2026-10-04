"""Lexical index seam — SQL storage and tenant-scoped search.

``LexicalIndex`` (see :mod:`app.services.rag.base`) is the keyword/BM25
retrieval abstraction. Two implementations live here:

* :class:`SqlLexicalIndex` — persistent ``document_chunks`` storage on the
  caller's own :class:`~sqlalchemy.ext.asyncio.AsyncSession`. Writes use
  ``flush()`` and **never** commit: the caller (``DocumentService``) owns the
  transaction, so chunk rows and the document status change atomically.
  Since milestone 3 it also implements :meth:`SqlLexicalIndex.search` — a
  read-only, tenant-fenced candidate generator (PostgreSQL GIN / SQLite
  FTS5). Search never flushes, commits or runs DDL, and it makes NO
  authorization decisions beyond the tenant fence: document visibility is
  applied afterwards by the retriever from the CURRENT database permissions.
* :class:`NullLexicalIndex` — the explicit no-op used whenever no database
  session is available. It is never a silent fallback from a real provider.

Storage details (milestone 2 added the storage; retrieval stays vector-only
by default — milestone 3 adds the lexical candidate path that a later hybrid
milestone will consume):

* Canonical rows always live in ``document_chunks`` (PostgreSQL and SQLite).
* On PostgreSQL, lexical search is served by the migration-created expression
  GIN index over ``to_tsvector('simple', text)``.
* On SQLite, an FTS5 mirror table (``document_chunks_fts``) is created at
  runtime — idempotently, because tests build the schema with
  ``Base.metadata.create_all()`` and virtual tables are not ORM-mapped. The
  mirror is written inside the SAME transaction/session as the canonical rows,
  so a rollback discards both together.

No ingest-time ``created_by`` / ``access`` / ``classification`` hints are ever
persisted: they are not authorization truth.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunk
from app.services.rag.base import RetrievedChunk
from app.services.rag.retriever import MAX_TOP_K

# FTS5 mirror: chunk identity + tenant/document metadata are UNINDEXED
# (stored, filterable, not tokenized); only ``text`` is searchable.
_FTS5_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    tenant_id UNINDEXED,
    document_id UNINDEXED,
    text
)
"""

_FTS5_INSERT = """
INSERT INTO document_chunks_fts (chunk_id, tenant_id, document_id, text)
VALUES (:chunk_id, :tenant_id, :document_id, :text)
"""

_FTS5_DELETE = """
DELETE FROM document_chunks_fts
WHERE tenant_id = :tenant_id AND document_id = :document_id
"""

# Milestone 3 — search. Phase 1 over the mirror: ranked chunk ids, tenant
# fence in SQL, bounded LIMIT, bm25 ASC (FTS5: more negative = better) with a
# chunk_id ASC tiebreak for deterministic ordering.
_FTS5_MATCH = """
SELECT chunk_id, bm25(document_chunks_fts) AS r
FROM document_chunks_fts
WHERE document_chunks_fts MATCH :match
  AND tenant_id = :tenant_id
ORDER BY r ASC, chunk_id ASC
LIMIT :fetch
"""

# Read-only mirror existence check — search never runs DDL, so a database
# that has never indexed anything simply yields no candidates.
_FTS5_EXISTS = (
    "SELECT count(*) FROM sqlite_master "
    "WHERE type = 'table' AND name = 'document_chunks_fts'"
)


def postgres_search_statement(collection_count: int = 0) -> str:
    """Static SQL for the PostgreSQL search branch.

    ``to_tsvector('simple', text)`` is byte-identical to the expression GIN
    index created by migration 0002, so the planner can use it — the config
    must never be switched silently. Only placeholder names (``:c0``, ``:c1``,
    ...) are composed here; every VALUE (query, tenant, collection ids, fetch)
    travels in the bound-params dict, never in the SQL text.
    """
    collection_clause = ""
    if collection_count:
        placeholders = ", ".join(f":c{i}" for i in range(collection_count))
        collection_clause = f" AND collection_id IN ({placeholders})"
    return (
        "SELECT chunk_id, document_id, collection_id, page, filename, text, "
        "chunk_index, ts_rank_cd(to_tsvector('simple', text), q) AS score "
        "FROM document_chunks, websearch_to_tsquery('simple', :query) AS q "
        "WHERE tenant_id = :tenant_id "
        "AND to_tsvector('simple', text) @@ q"
        f"{collection_clause} "
        "ORDER BY score DESC, chunk_id ASC "
        "LIMIT :fetch"
    )


def _fts_tokens(query: str) -> list[str]:
    """Sanitize a user query into plain alphanumeric tokens.

    Both engines search ONLY these tokens (SQLite as quoted phrases,
    PostgreSQL as websearch words), so quotes, parentheses, ``*``, ``NEAR``,
    column selectors and malformed FTS expressions can never inject syntax
    or raise — they tokenize into inert words. The uppercase boolean
    operators websearch understands (``AND``/``OR``/``NOT``, any case) are
    dropped so both engines apply the same strict implicit-AND semantics.
    """
    tokens: list[str] = []
    current: list[str] = []
    for char in query or "":
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return [token for token in tokens if token.upper() not in ("AND", "OR", "NOT")]


def _bounded_fetch(top_k: Any) -> int | None:
    """Clamp ``top_k`` to the retrieval hard cap; unusable values yield none.

    Reuses ``retriever.MAX_TOP_K`` (50) — the same ceiling the API already
    enforces. Callers going through ``_initial_fetch`` stay within
    ``MAX_CANDIDATES`` (40) as well. No new limit is introduced here.
    """
    try:
        limit = int(top_k)
    except (TypeError, ValueError):
        return None
    if limit <= 0:
        return None
    return min(limit, MAX_TOP_K)


class SqlLexicalIndex:
    """Persistent :class:`LexicalIndex` bound to the caller's session.

    Transaction contract: every write is ``flush()``-only. Durability, and the
    rollback that discards staged rows on ingestion failure, belong to the
    caller — this class never calls ``commit()``.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @property
    def _dialect(self) -> str:
        bind = self.db.bind
        return bind.dialect.name if bind is not None else ""

    @property
    def _uses_fts5(self) -> bool:
        return self._dialect == "sqlite"

    # -------------------------------------------------------------- searching
    async def search(
        self,
        *,
        query: str,
        tenant_id: str,
        collection_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        """Tenant-scoped lexical candidate generation (milestone 3).

        Read-only: SELECT statements only, executed with autoflush disabled
        so a caller's pending state is never flushed, committed or mutated —
        no DDL either (a database with no FTS mirror simply yields ``[]``).

        This method is a candidate generator, NOT an authorization layer:
        beyond the mandatory tenant fence (and the optional collection
        filter) it returns raw candidates. Deciding who may READ a document
        is the retriever's job, via the CURRENT database permissions.

        Ordering is deterministic (engine rank, then ``chunk_id``) and the
        result never exceeds ``min(top_k, MAX_TOP_K)`` hits.
        """
        fetch = _bounded_fetch(top_k)
        if fetch is None:
            return []
        tokens = _fts_tokens(query)
        if not tokens:
            return []
        try:
            tenant_uuid = uuid.UUID(tenant_id)
        except ValueError:
            return []  # fail closed: a malformed server-derived tenant finds nothing
        collections: list[uuid.UUID] | None = None
        if collection_ids:
            try:
                collections = [uuid.UUID(str(value)) for value in collection_ids]
            except ValueError:
                return []  # fail closed: an unusable collection filter finds nothing

        if self._uses_fts5:
            return await self._search_fts5(tenant_uuid, collections, tokens, fetch)
        if self._dialect == "postgresql":
            return await self._search_postgres(tenant_uuid, collections, tokens, fetch)
        return []  # unknown engine — fail closed

    async def _search_fts5(
        self,
        tenant_uuid: uuid.UUID,
        collections: list[uuid.UUID] | None,
        tokens: list[str],
        fetch: int,
    ) -> list[RetrievedChunk]:
        """Phase 1: ranked chunk ids from the FTS5 mirror; phase 2: hydrate
        canonical rows (which re-asserts the tenant fence and applies the
        collection filter — the mirror is never trusted alone for metadata)."""
        match = " ".join(f'"{token}"' for token in tokens)
        with self.db.sync_session.no_autoflush:
            exists = (await self.db.execute(text(_FTS5_EXISTS))).scalar_one()
            if not exists:
                return []
            ranked = (
                await self.db.execute(
                    text(_FTS5_MATCH),
                    {
                        "match": match,
                        "tenant_id": str(tenant_uuid),
                        "fetch": fetch,
                    },
                )
            ).fetchall()
            if not ranked:
                return []

            # FTS5 bm25() is negative with smaller = better; flip it so the
            # shared RetrievedChunk score stays positive higher-is-better
            score_by_chunk = {row[0]: -float(row[1]) for row in ranked}
            ordered_ids = list(score_by_chunk)

            stmt = select(DocumentChunk).where(
                DocumentChunk.tenant_id == tenant_uuid,
                DocumentChunk.chunk_id.in_(ordered_ids),
            )
            if collections is not None:
                stmt = stmt.where(DocumentChunk.collection_id.in_(collections))
            rows = (await self.db.execute(stmt)).scalars().all()

        by_chunk_id = {row.chunk_id: row for row in rows}
        results: list[RetrievedChunk] = []
        for chunk_id in ordered_ids:  # phase-1 rank order preserved
            row = by_chunk_id.get(chunk_id)
            if row is None:
                continue  # dropped by the tenant/collection fence (or stale mirror)
            results.append(self._chunk_from_row(row, score_by_chunk[chunk_id]))
        return results

    async def _search_postgres(
        self,
        tenant_uuid: uuid.UUID,
        collections: list[uuid.UUID] | None,
        tokens: list[str],
        fetch: int,
    ) -> list[RetrievedChunk]:
        """Single ranked query against the GIN-indexed tsvector expression.

        `websearch_to_tsquery` accepts arbitrary input safely and the tokens
        handed to it are already sanitised by :func:`_fts_tokens`.
        """
        sql = postgres_search_statement(0 if collections is None else len(collections))
        params: dict[str, Any] = {
            "query": " ".join(tokens),
            "tenant_id": str(tenant_uuid),
            "fetch": fetch,
        }
        if collections:
            params.update({f"c{i}": str(value) for i, value in enumerate(collections)})
        with self.db.sync_session.no_autoflush:
            rows = (await self.db.execute(text(sql), params)).fetchall()
        return [
            RetrievedChunk(
                text=str(row.text),
                score=float(row.score),
                document_id=str(row.document_id),
                collection_id=str(row.collection_id) if row.collection_id else None,
                page_number=int(row.page),
                quote=str(row.text)[:200],
                chunk_id=str(row.chunk_id),
                filename=str(row.filename),
                metadata={"chunk_index": int(row.chunk_index)},
            )
            for row in rows
        ]

    @staticmethod
    def _chunk_from_row(row: DocumentChunk, score: float) -> RetrievedChunk:
        """Map a canonical row to the shared retrieval model.

        Only retrieval/storage fields are exposed; ``created_by``/``access``/
        ``classification`` are never stored on chunks and never consulted.
        """
        return RetrievedChunk(
            text=row.text,
            score=score,
            document_id=str(row.document_id),
            collection_id=str(row.collection_id) if row.collection_id else None,
            page_number=row.page,
            quote=row.text[:200],
            chunk_id=row.chunk_id,
            filename=row.filename,
            metadata={"chunk_index": row.chunk_index},
        )

    # --------------------------------------------------------------- writing
    async def replace_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        payloads: list[dict[str, Any]],
    ) -> None:
        """Replace every lexical record of one document (idempotent re-ingest).

        Tenant and document identity come from the method arguments — both
        are server-derived by the caller; payload-level ``tenant_id`` /
        ``document_id`` entries are never trusted here. Authorization hints
        inside payloads are ignored: only retrieval fields are stored.
        """
        tenant_uuid = uuid.UUID(tenant_id)
        document_uuid = uuid.UUID(document_id)

        await self._ensure_fts5()
        await self._delete_rows(tenant_uuid, document_uuid)

        rows: list[dict[str, Any]] = []
        for payload in payloads:
            chunk_id = str(payload["chunk_id"])
            text_value = str(payload["text"])
            self.db.add(
                DocumentChunk(
                    tenant_id=tenant_uuid,
                    document_id=document_uuid,
                    collection_id=_collection_id(payload),
                    chunk_id=chunk_id,
                    chunk_index=int(payload.get("chunk_index", 0)),
                    page=int(payload.get("page", 1)),
                    filename=str(payload.get("filename", ""))[:400],
                    text=text_value,
                )
            )
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "tenant_id": str(tenant_uuid),
                    "document_id": str(document_uuid),
                    "text": text_value,
                }
            )
        await self.db.flush()
        if rows and self._uses_fts5:
            await self.db.execute(text(_FTS5_INSERT), rows)

    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        """Remove every lexical record of one document inside one tenant.

        Safe no-op for an unknown document; rows of other tenants (or other
        documents) are never touched.
        """
        tenant_uuid = uuid.UUID(tenant_id)
        document_uuid = uuid.UUID(document_id)
        await self._ensure_fts5()
        await self._delete_rows(tenant_uuid, document_uuid)
        await self.db.flush()

    # ------------------------------------------------------------ internals
    async def _delete_rows(self, tenant_uuid: uuid.UUID, document_uuid: uuid.UUID) -> None:
        await self.db.execute(
            sql_delete(DocumentChunk).where(
                DocumentChunk.tenant_id == tenant_uuid,
                DocumentChunk.document_id == document_uuid,
            )
        )
        if self._uses_fts5:
            await self.db.execute(
                text(_FTS5_DELETE),
                {"tenant_id": str(tenant_uuid), "document_id": str(document_uuid)},
            )

    async def _ensure_fts5(self) -> None:
        """Idempotent runtime DDL — SQLite only (PostgreSQL uses the GIN index).

        Runs BEFORE any DML of the transaction so the driver's DDL handling
        cannot interleave with staged row writes.
        """
        if self._uses_fts5:
            await self.db.execute(text(_FTS5_DDL))


def _collection_id(payload: dict[str, Any]) -> uuid.UUID | None:
    raw = payload.get("collection_id")
    if not raw:
        return None
    return uuid.UUID(str(raw))


class NullLexicalIndex:
    """No-op ``LexicalIndex`` — lexical retrieval is not implemented.

    * ``search`` returns no candidates, so nothing can be fused or ranked
      from the lexical path.
    * ``replace_document`` records nothing — no content becomes searchable.
    * ``delete_document`` is a safe no-op — there is nothing to remove.

    Used whenever no database session is available (see
    :func:`app.services.rag.get_lexical_index`); never a silent fallback
    from a configured provider.
    """

    async def search(
        self,
        *,
        query: str,
        tenant_id: str,
        collection_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        """Return no lexical candidates (lexical search is not implemented)."""
        return []

    async def replace_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        payloads: list[dict[str, Any]],
    ) -> None:
        """No-op: nothing is indexed, so nothing becomes searchable."""
        return None

    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        """No-op: the null index never holds data to remove."""
        return None


__all__ = ["NullLexicalIndex", "SqlLexicalIndex"]
