"""Conversation and API key repositories."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ApiKey, Conversation, Message


class ConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
            )
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
    ) -> Conversation | None:
        """Tenant-scoped (and optionally owner-scoped) fetch."""
        query = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        if user_id is not None:
            query = query.where(Conversation.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def add(self, conversation: Conversation) -> Conversation:
        self.db.add(conversation)
        await self.db.flush()
        return conversation

    async def delete(self, conversation: Conversation) -> None:
        await self.db.delete(conversation)
        await self.db.flush()

    async def get_message(
        self, tenant_id: uuid.UUID, message_id: uuid.UUID
    ) -> tuple[Message, Conversation] | None:
        """Resolve a message through its conversation's tenant scope."""
        result = await self.db.execute(
            select(Message, Conversation)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Message.id == message_id, Conversation.tenant_id == tenant_id)
        )
        row = result.one_or_none()
        return row if row else None

    async def add_message(self, message: Message) -> Message:
        self.db.add(message)
        await self.db.flush()
        return message


class ApiKeyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self, tenant_id: uuid.UUID, *, include_revoked: bool = False
    ) -> list[ApiKey]:
        query = select(ApiKey).where(ApiKey.tenant_id == tenant_id)
        if not include_revoked:
            query = query.where(ApiKey.revoked_at.is_(None))
        query = query.order_by(ApiKey.created_at.desc())
        return list((await self.db.execute(query)).scalars().all())

    async def get(self, tenant_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey | None:
        result = await self.db.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def add(self, key: ApiKey) -> ApiKey:
        self.db.add(key)
        await self.db.flush()
        return key
