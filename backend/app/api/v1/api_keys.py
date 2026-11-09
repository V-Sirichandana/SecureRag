"""API key routes — ADMIN+ (raw key returned exactly once)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.dependencies import (
    CurrentTenant,
    CurrentUser,
    DbSession,
    client_context,
    require_permission,
)
from app.schemas.api_key import ApiKeyCreatedOut, ApiKeyCreateIn, ApiKeyOut
from app.services.api_key_service import ApiKeyService

api_keys_router = APIRouter(prefix="/api-keys", tags=["API Keys"])

MANAGE_KEYS = [Depends(require_permission("manage_api_keys"))]


@api_keys_router.get("", response_model=list[ApiKeyOut], summary="List API keys")
async def list_api_keys(tenant: CurrentTenant, db: DbSession) -> list[ApiKeyOut]:
    return await ApiKeyService(db).list_keys(tenant=tenant)


@api_keys_router.post(
    "",
    response_model=ApiKeyCreatedOut,
    status_code=201,
    summary="Create an API key (plaintext returned once)",
    dependencies=MANAGE_KEYS,
)
async def create_api_key(
    payload: ApiKeyCreateIn,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> ApiKeyCreatedOut:
    ip_address, user_agent = client_context(request)
    return await ApiKeyService(db).create_key(
        tenant=tenant,
        user=user,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@api_keys_router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    dependencies=MANAGE_KEYS,
)
async def revoke_api_key(
    key_id: UUID,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    ip_address, user_agent = client_context(request)
    await ApiKeyService(db).revoke_key(
        tenant=tenant,
        user=user,
        key_id=key_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
