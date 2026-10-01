"""Global search route (frontend contract)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentTenant, DbSession
from app.schemas.settings import SearchResultOut
from app.services.search_service import SearchService

search_router = APIRouter(prefix="/search", tags=["Search"])


@search_router.get("", response_model=list[SearchResultOut], summary="Search the organization")
async def search(
    tenant: CurrentTenant,
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=200)] = "",
) -> list[SearchResultOut]:
    return await SearchService(db).search(tenant=tenant, query=q)
