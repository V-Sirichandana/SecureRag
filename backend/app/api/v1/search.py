"""Global search + semantic retrieval routes (frontend contract)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import (
    AppSettings,
    CurrentTenant,
    CurrentUser,
    DbSession,
    VectorStoreDep,
    require_permission,
)
from app.schemas.retrieval import RetrievedChunkOut, RetrieveIn
from app.schemas.settings import SearchResultOut
from app.services.rag import get_retriever
from app.services.rag.base import RetrievedChunk
from app.services.search_service import SearchService

search_router = APIRouter(prefix="/search", tags=["Search"])


@search_router.get("", response_model=list[SearchResultOut], summary="Search the organization")
async def search(
    tenant: CurrentTenant,
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=200)] = "",
) -> list[SearchResultOut]:
    return await SearchService(db).search(tenant=tenant, query=q)


def _out(chunk: RetrievedChunk) -> RetrievedChunkOut:
    return RetrievedChunkOut(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        collection_id=chunk.collection_id,
        content=chunk.text,
        score=chunk.score,
        page=chunk.page_number,
        filename=chunk.filename,
        metadata=chunk.metadata,
        rerank_score=chunk.rerank_score,
    )


@search_router.post(
    "/retrieve",
    response_model=list[RetrievedChunkOut],
    summary="Permission-aware semantic retrieval",
    dependencies=[Depends(require_permission("view_documents"))],
)
async def retrieve(
    payload: RetrieveIn,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    vector_store: VectorStoreDep,
) -> list[RetrievedChunkOut]:
    """Tenant-scoped similarity search over indexed document chunks.

    The tenant and user come from the authenticated principal; document
    visibility is checked against CURRENT permissions in the database on
    every request. The request body cannot influence either. The retrieval
    mode (vector/hybrid) and the meaning of ``score`` are server-side
    configuration — the request body cannot select them.
    """
    retriever = get_retriever(settings, db=db, vector_store=vector_store)
    chunks = await retriever.retrieve(
        query=payload.query,
        tenant_id=str(tenant.id),
        user_id=str(user.id),
        top_k=payload.top_k,
    )
    return [_out(chunk) for chunk in chunks]
