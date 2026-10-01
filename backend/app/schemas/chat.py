"""Chat / conversation schemas (frontend contracts)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import APIModel, UTCDateTime


class ChatMessageOut(APIModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    citations: list[dict[str, Any]] | None = None
    created_at: UTCDateTime
    model: str | None = None
    latency_ms: int | None = None
    token_count: int | None = None
    feedback: Literal["up", "down"] | None = None


class ConversationOut(APIModel):
    id: str
    title: str
    collection_id: str | None = None
    updated_at: UTCDateTime
    message_count: int = 0
    messages: list[ChatMessageOut] = []


class ConversationCreateIn(APIModel):
    title: str = Field(default="New conversation", min_length=1, max_length=300)
    collection_id: str | None = None


class MessageCreateIn(APIModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    citations: list[dict[str, Any]] | None = None
    model: str | None = Field(default=None, max_length=80)
    latency_ms: int | None = Field(default=None, ge=0)
    token_count: int | None = Field(default=None, ge=0)


class FeedbackIn(APIModel):
    feedback: Literal["up", "down"]
