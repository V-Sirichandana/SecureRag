"""Collection routes — tenant-scoped CRUD."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.dependencies import (
    CurrentMembership,
    CurrentTenant,
    CurrentUser,
    DbSession,
    client_context,
    require_permission,
)
from app.schemas.collection import CollectionCreateIn, CollectionOut, CollectionUpdateIn
from app.services.collection_service import CollectionService

collections_router = APIRouter(prefix="/collections", tags=["Collections"])


@collections_router.get("", response_model=list[CollectionOut], summary="List collections")
async def list_collections(tenant: CurrentTenant, db: DbSession) -> list[CollectionOut]:
    return await CollectionService(db).list_collections(tenant=tenant)


@collections_router.post(
    "",
    response_model=CollectionOut,
    status_code=201,
    summary="Create a collection",
    dependencies=[Depends(require_permission("manage_collections"))],
)
async def create_collection(
    payload: CollectionCreateIn,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> CollectionOut:
    ip_address, user_agent = client_context(request)
    return await CollectionService(db).create_collection(
        tenant=tenant,
        user=user,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@collections_router.get(
    "/{collection_id}", response_model=CollectionOut, summary="Fetch a collection"
)
async def get_collection(
    collection_id: UUID,
    tenant: CurrentTenant,
    db: DbSession,
) -> CollectionOut:
    return await CollectionService(db).get_collection_out(
        tenant=tenant, collection_id=collection_id
    )


@collections_router.patch(
    "/{collection_id}",
    response_model=CollectionOut,
    summary="Update a collection",
)
async def update_collection(
    collection_id: UUID,
    payload: CollectionUpdateIn,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
) -> CollectionOut:
    ip_address, user_agent = client_context(request)
    return await CollectionService(db).update_collection(
        tenant=tenant,
        user=user,
        role=membership.role,
        collection_id=collection_id,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@collections_router.delete(
    "/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a collection (documents are kept, unfiled)",
)
async def delete_collection(
    collection_id: UUID,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
) -> Response:
    ip_address, user_agent = client_context(request)
    await CollectionService(db).delete_collection(
        tenant=tenant,
        user=user,
        role=membership.role,
        collection_id=collection_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
