"""Retrieval request/response schemas (POST /search/retrieve)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import APIModel

MAX_QUERY_LENGTH = 1000
MAX_TOP_K = 50


class RetrieveIn(APIModel):
    """Only parameters the client may legitimately control.

    Tenant and document authorization are derived server-side — there is
    intentionally no ``tenant_id`` or document allow-list field here.
    """

    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    top_k: int = Field(default=10, ge=1, le=MAX_TOP_K)


class RetrievedChunkOut(APIModel):
    """One authorized retrieval hit.

    ``score`` is the original vector-search similarity (never overwritten).
    ``rerankScore`` is the optional provider-specific reranker score, null
    when no reranking was applied. The two are different scales and are not
    directly comparable across reranker providers.
    """

    chunk_id: str
    document_id: str
    collection_id: str | None = None
    content: str
    score: float
    page: int = 1
    filename: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    rerank_score: float | None = None
