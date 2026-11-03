"""Chat service — conversations and messages, scoped to tenant AND owner.

The ``role="user"`` branch of :meth:`ChatService.persist_message` is the
question flow: retrieve authorized chunks through the existing tenant- and
permission-scoped retriever, bound them, generate a grounded answer through
the configured :class:`LLMProvider`, build citations from the retrieved
chunks (never from model output) and persist both messages + the QUERY audit
event in one transaction. Tenant and user identity come exclusively from the
authenticated principal; the request body cannot influence retrieval scope.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError, ServiceNotConfiguredError
from app.models import Collection, Conversation, Message, Tenant, User
from app.repositories import CollectionRepository, ConversationRepository
from app.schemas.chat import (
    ChatMessageOut,
    ConversationCreateIn,
    ConversationOut,
    FeedbackIn,
    MessageCreateIn,
)
from app.services.audit_service import AuditService
from app.services.rag import get_llm_provider, get_retriever
from app.services.rag.answer import SYSTEM_PROMPT, bound_context, build_citations
from app.services.rag.base import RetrievedChunk, VectorStore

logger = logging.getLogger("securerag.chat")

DEFAULT_TITLE = "New conversation"

# retrieval size for one question — the same bound the context builder sends
CHAT_TOP_K = 8
MAX_MODEL_LENGTH = 80


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
    def __init__(
        self,
        db: AsyncSession,
        *,
        settings: Settings | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.db = db
        self.repository = ConversationRepository(db)
        self.audit = AuditService(db)
        # generation context — supplied by the chat route for question flow
        self.settings = settings
        self.vector_store = vector_store

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
        """Persist one message — for ``role="user"`` this is the question flow.

        Order of operations: tenant + owner scoped conversation fetch →
        retrieval through the existing permission-checked retriever → bounded
        context → provider generation → citations built from the retrieved
        chunks → user message, title update, QUERY audit and the generated
        assistant message committed together. Generation happens BEFORE any
        write, so a provider/configuration failure persists nothing and never
        substitutes a fake answer. Returns the generated assistant message for
        questions (the persisted message otherwise).
        """
        conversation = await self.repository.get(
            tenant.id, conversation_id, user_id=user.id
        )
        if conversation is None:
            raise NotFoundError("CONVERSATION_NOT_FOUND")

        assistant_message: Message | None = None
        if payload.role == "user":
            assistant_message = await self._generate_answer(
                tenant=tenant,
                user=user,
                conversation=conversation,
                question=payload.content,
            )

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

        if assistant_message is not None:
            # built by _generate_answer AFTER the user message, so message
            # ordering by created_at always puts the question first
            await self.repository.add_message(assistant_message)

        await self.db.commit()
        if assistant_message is not None:
            return serialize_message(assistant_message)
        return serialize_message(message)

    async def _generate_answer(
        self,
        *,
        tenant: Tenant,
        user: User,
        conversation: Conversation,
        question: str,
    ) -> Message:
        """Retrieve authorized chunks and produce the grounded assistant message.

        Fails fast with SERVICE_NOT_CONFIGURED (501) when no provider is
        configured — a real generation request never falls back to a canned or
        simulated answer. Retrieval reuses the existing factory and
        tenant/permission boundary; only the conversation's collection (when
        set) further narrows the scope.
        """
        if self.settings is None or self.vector_store is None:
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED", "Answer generation is not configured."
            )

        # resolve configuration BEFORE retrieval so an unconfigured deployment
        # answers 501 without doing any retrieval or upstream work
        provider = get_llm_provider(self.settings)

        retriever = get_retriever(
            self.settings, db=self.db, vector_store=self.vector_store
        )
        collection_ids = (
            [str(conversation.collection_id)] if conversation.collection_id else None
        )
        chunks = await retriever.retrieve(
            query=question,
            tenant_id=str(tenant.id),
            user_id=str(user.id),
            collection_ids=collection_ids,
            top_k=CHAT_TOP_K,
        )
        context = bound_context(chunks)
        collection_names = await self._collection_names(tenant, context)

        try:
            result = await provider.generate(
                system=SYSTEM_PROMPT,
                prompt=question,
                context=context,
            )
        except AppError:
            raise  # SERVICE_NOT_CONFIGURED / SERVICE_UNAVAILABLE keep their status
        except Exception as exc:  # noqa: BLE001 - never leak provider internals
            logger.exception("Answer generation failed")
            raise AppError("SERVICE_UNAVAILABLE") from exc

        content = (result.content or "").strip()
        if not content:
            raise AppError(
                "SERVICE_UNAVAILABLE", "The answer provider returned an empty response."
            )

        return Message(
            conversation_id=conversation.id,
            role="assistant",
            content=content,
            # rebuilt from the retrieved chunks above — model output only
            # supplies which [n] markers appear in the answer text
            citations=build_citations(content, context, collection_names),
            model=(result.model or "").strip()[:MAX_MODEL_LENGTH] or None,
            latency_ms=max(0, int(result.latency_ms or 0)),
            token_count=max(0, int(result.token_count or 0)),
        )

    async def _collection_names(
        self, tenant: Tenant, context: list[RetrievedChunk]
    ) -> dict[str, str]:
        """Tenant-scoped display names for the context's collections only."""
        ids: set[uuid.UUID] = set()
        for chunk in context:
            if not chunk.collection_id:
                continue
            try:
                ids.add(uuid.UUID(str(chunk.collection_id)))
            except ValueError:
                continue  # malformed payload id — no display name
        if not ids:
            return {}
        rows = (
            await self.db.execute(
                select(Collection.id, Collection.name).where(
                    Collection.tenant_id == tenant.id, Collection.id.in_(ids)
                )
            )
        ).all()
        return {str(collection_id): name for collection_id, name in rows}

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

