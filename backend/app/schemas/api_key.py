"""API key schemas (frontend ApiKey contract)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel, UTCDateTime


class ApiKeyOut(APIModel):
    id: str
    name: str
    environment: Literal["live", "test"]
    masked_key: str
    created_at: UTCDateTime
    last_used_at: UTCDateTime | None = None
    expires_at: UTCDateTime | None = None
    permissions: list[str] = []


class ApiKeyCreateIn(APIModel):
    name: str = Field(min_length=1, max_length=200)
    environment: Literal["live", "test"] = "test"
    expiration: Literal["never", "30", "90", "365"] = "never"
    permissions: list[str] = Field(default_factory=list, max_length=50)


class ApiKeyCreatedOut(APIModel):
    """Creation response — ``plaintext`` is shown exactly once."""

    key: ApiKeyOut
    plaintext: str
