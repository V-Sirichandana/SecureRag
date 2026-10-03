"""Lexical index seam — SQL storage implementation and the no-op provider.

``LexicalIndex`` (see :mod:`app.services.rag.base`) is the keyword/BM25
retrieval abstraction. Two implementations live here:

* :class:`SqlLexicalIndex` — persistent ``document_chunks`` storage on the
  caller's own :class:`~sqlalchemy.ext.asyncio.AsyncSession`. Writes use
  ``flush()`` and **never** commit: the caller (``DocumentService``) owns the
  transaction, so chunk rows and the document status change atomically.
* :class:`NullLexicalIndex` — the explicit no-op used whenever no database
  session is available. It is never a silent fallback from a real provider.

Storage details (milestone 2 — storage only, retrieval stays vector-only):

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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunk
from app.services.rag.base import RetrievedChunk

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
        """Not implemented in milestone 2 — storage only.

        Hybrid retrieval activates in a later milestone; until then the
        retriever never consults the lexical index, so returning no
        candidates keeps retrieval vector-only.
        """
        return []

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
