"""Chat routes — conversations and messages (tenant + owner scoped)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from app.core.dependencies import (
    CurrentTenant,
    CurrentUser,
    DbSession,
    client_context,
)
from app.schemas.chat import (
    ChatMessageOut,
    ConversationCreateIn,
    ConversationOut,
    FeedbackIn,
    MessageCreateIn,
)
from app.services.chat_service import ChatService

chat_router = APIRouter(prefix="/chat", tags=["Chat"])


@chat_router.get(
    "/conversations", response_model=list[ConversationOut], summary="List conversations"
)
async def list_conversations(
    tenant: CurrentTenant, user: CurrentUser, db: DbSession
) -> list[ConversationOut]:
    return await ChatService(db).list_conversations(tenant=tenant, user=user)


@chat_router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=201,
    summary="Start a conversation",
)
async def create_conversation(
    payload: ConversationCreateIn,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> ConversationOut:
    return await ChatService(db).create_conversation(
        tenant=tenant, user=user, payload=payload
    )


@chat_router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
    summary="Fetch a conversation with messages",
)
async def get_conversation(
    conversation_id: UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> ConversationOut:
    return await ChatService(db).get_conversation(
        tenant=tenant, user=user, conversation_id=conversation_id
    )


@chat_router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
)
async def delete_conversation(
    conversation_id: UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    await ChatService(db).delete_conversation(
        tenant=tenant, user=user, conversation_id=conversation_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@chat_router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageOut,
    status_code=201,
    summary="Persist a message (audit: QUERY)",
)
async def persist_message(
    conversation_id: UUID,
    payload: MessageCreateIn,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> ChatMessageOut:
    ip_address, user_agent = client_context(request)
    return await ChatService(db).persist_message(
        tenant=tenant,
        user=user,
        conversation_id=conversation_id,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@chat_router.post(
    "/messages/{message_id}/feedback",
    status_code=204,
    summary="Record message feedback",
)
async def submit_feedback(
    message_id: UUID,
    payload: FeedbackIn,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    await ChatService(db).submit_feedback(
        tenant=tenant, user=user, message_id=message_id, payload=payload
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
