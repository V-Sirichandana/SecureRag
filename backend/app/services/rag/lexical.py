"""Lexical index seam — the explicit no-op provider (milestone 1).

``LexicalIndex`` (see :mod:`app.services.rag.base`) is the future
keyword/BM25 retrieval abstraction. Until a real backend exists the
factory resolves :class:`NullLexicalIndex`, which states plainly that
lexical indexing is not implemented — it is never a silent fallback
from a configured provider.
"""

from __future__ import annotations

from typing import Any

from app.services.rag.base import RetrievedChunk


class NullLexicalIndex:
    """No-op ``LexicalIndex`` — lexical retrieval is not implemented.

    * ``search`` returns no candidates, so nothing can be fused or ranked
      from the lexical path.
    * ``replace_document`` records nothing — no content becomes searchable.
    * ``delete_document`` is a safe no-op — there is nothing to remove.

    This is the single explicit provider while lexical indexing does not
    exist. A future configured provider must never silently degrade to it.
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


__all__ = ["NullLexicalIndex"]
