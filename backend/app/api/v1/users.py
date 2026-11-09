"""User management routes (member directory, invites, role/status changes)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.dependencies import (
    AppSettings,
    CurrentMembership,
    CurrentTenant,
    CurrentUser,
    DbSession,
    client_context,
    require_permission,
)
from app.schemas.user import InviteUserIn, InviteUserOut, UpdateUserIn, UserOut
from app.services.user_service import UserService, serialize_user

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.get("", response_model=list[UserOut], summary="Members of the organization")
async def list_users(tenant: CurrentTenant, db: DbSession) -> list[UserOut]:
    return await UserService(db).list_users(tenant=tenant)


@users_router.get("/{user_id}", response_model=UserOut, summary="Fetch one member")
async def get_user(
    user_id: UUID, tenant: CurrentTenant, db: DbSession
) -> UserOut:
    service = UserService(db)
    membership, user = await service.get_membership(tenant=tenant, user_id=user_id)
    return serialize_user(user, membership)


@users_router.post(
    "/invite",
    response_model=InviteUserOut,
    status_code=201,
    summary="Invite a user to the organization",
    dependencies=[Depends(require_permission("manage_users"))],
)
async def invite_user(
    payload: InviteUserIn,
    request: Request,
    tenant: CurrentTenant,
    actor: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
    settings: AppSettings,
) -> InviteUserOut:
    ip_address, user_agent = client_context(request)
    return await UserService(db).invite_user(
        tenant=tenant,
        actor=actor,
        actor_role=membership.role,
        payload=payload,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@users_router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="Update a member's role or status",
    dependencies=[Depends(require_permission("manage_users"))],
)
async def update_user(
    user_id: UUID,
    payload: UpdateUserIn,
    request: Request,
    tenant: CurrentTenant,
    actor: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
) -> UserOut:
    ip_address, user_agent = client_context(request)
    return await UserService(db).update_user(
        tenant=tenant,
        actor=actor,
        actor_role=membership.role,
        user_id=user_id,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@users_router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from the organization",
    dependencies=[Depends(require_permission("manage_users"))],
)
async def remove_user(
    user_id: UUID,
    request: Request,
    tenant: CurrentTenant,
    actor: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
) -> Response:
    ip_address, user_agent = client_context(request)
    await UserService(db).remove_user(
        tenant=tenant,
        actor=actor,
        actor_role=membership.role,
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
