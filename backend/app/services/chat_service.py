"""Chat service — conversations and messages, scoped to tenant AND owner."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Conversation, Message, Tenant, User
from app.repositories import CollectionRepository, ConversationRepository
from app.schemas.chat import (
    ChatMessageOut,
    ConversationCreateIn,
    ConversationOut,
    FeedbackIn,
    MessageCreateIn,
)
from app.services.audit_service import AuditService

DEFAULT_TITLE = "New conversation"


def serialize_message(message: Message) -> ChatMessageOut:
    return ChatMessageOut(
        id=str(message.id),
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        citations=message.citations,
        created_at=message.created_at,
        model=message.model,
        latency_ms=message.latency_ms,
        token_count=message.token_count,
        feedback=message.feedback,  # type: ignore[arg-type]
    )


def serialize_conversation(conversation: Conversation) -> ConversationOut:
    messages = sorted(conversation.messages, key=lambda item: item.created_at)
    return ConversationOut(
        id=str(conversation.id),
        title=conversation.title,
        collection_id=str(conversation.collection_id) if conversation.collection_id else None,
        updated_at=conversation.updated_at,
        message_count=len(messages),
        messages=[serialize_message(message) for message in messages],
    )


class ChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ConversationRepository(db)
        self.audit = AuditService(db)

    async def list_conversations(
        self, *, tenant: Tenant, user: User
    ) -> list[ConversationOut]:
        rows = await self.repository.list_for_user(tenant.id, user.id)
        return [serialize_conversation(conversation) for conversation in rows]

    async def get_conversation(
        self, *, tenant: Tenant, user: User, conversation_id: uuid.UUID
    ) -> ConversationOut:
        conversation = await self.repository.get(
            tenant.id, conversation_id, user_id=user.id
        )
        if conversation is None:
            raise NotFoundError("CONVERSATION_NOT_FOUND")
        return serialize_conversation(conversation)

    async def create_conversation(
        self,
        *,
        tenant: Tenant,
        user: User,
        payload: ConversationCreateIn,
    ) -> ConversationOut:
        collection_id = None
        if payload.collection_id:
            collection = await CollectionRepository(self.db).get(
                tenant.id, uuid.UUID(payload.collection_id)
            )
            if collection is None:
                raise NotFoundError("COLLECTION_NOT_FOUND")
            collection_id = collection.id

        conversation = Conversation(
            tenant_id=tenant.id,
            user_id=user.id,
            title=payload.title,
            collection_id=collection_id,
            # new conversations have no messages yet; initialize the collection
            # so serialization never triggers a lazy load
            messages=[],
        )
        await self.repository.add(conversation)
        await self.db.commit()
        return serialize_conversation(conversation)

    async def delete_conversation(
        self, *, tenant: Tenant, user: User, conversation_id: uuid.UUID
    ) -> None:
        conversation = await self.repository.get(
            tenant.id, conversation_id, user_id=user.id
        )
        if conversation is None:
            raise NotFoundError("CONVERSATION_NOT_FOUND")
        await self.repository.delete(conversation)
        await self.db.commit()

    async def persist_message(
        self,
        *,
        tenant: Tenant,
        user: User,
        conversation_id: uuid.UUID,
        payload: MessageCreateIn,
        ip_address: str | None,
        user_agent: str | None,
    ) -> ChatMessageOut:
        conversation = await self.repository.get(
            tenant.id, conversation_id, user_id=user.id
        )
        if conversation is None:
            raise NotFoundError("CONVERSATION_NOT_FOUND")

        message = Message(
            conversation_id=conversation.id,
            role=payload.role,
            content=payload.content,
            citations=payload.citations,
            model=payload.model,
            latency_ms=payload.latency_ms,
            token_count=payload.token_count,
        )
        await self.repository.add_message(message)

        conversation.updated_at = datetime.now(UTC)
        if conversation.title == DEFAULT_TITLE and payload.role == "user":
            conversation.title = payload.content[:48]

        if payload.role == "user":
            await self.audit.log(
                user=user,
                tenant=tenant,
                action="QUERY",
                resource_type="conversation",
                resource_id=conversation.id,
                resource_label=conversation.title,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"preview": payload.content[:120]},
            )
        await self.db.commit()
        return serialize_message(message)

    async def submit_feedback(
        self,
        *,
        tenant: Tenant,
        user: User,
        message_id: uuid.UUID,
        payload: FeedbackIn,
    ) -> None:
        resolved = await self.repository.get_message(tenant.id, message_id)
        if resolved is None:
            raise NotFoundError("MESSAGE_NOT_FOUND")
        message, conversation = resolved
        if conversation.user_id != user.id:
            raise NotFoundError("MESSAGE_NOT_FOUND")
        message.feedback = payload.feedback
        await self.db.commit()

