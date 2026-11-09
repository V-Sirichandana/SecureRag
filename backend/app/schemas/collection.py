"""Collection schemas (frontend Collection contract)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import APIModel, UTCDateTime

VisibilityLiteral = Literal["everyone", "members", "restricted"]


class CollectionOut(APIModel):
    id: str
    name: str
    description: str = ""
    document_count: int = 0
    owner: str = ""
    updated_at: UTCDateTime
    visibility: VisibilityLiteral = "everyone"
    color: str = "#6366f1"


class CollectionCreateIn(APIModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    visibility: VisibilityLiteral = "everyone"
    color: str | None = Field(default=None, max_length=16)


class CollectionUpdateIn(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    visibility: VisibilityLiteral | None = None
    color: str | None = Field(default=None, max_length=16)

    @model_validator(mode="after")
    def _at_least_one(self) -> CollectionUpdateIn:
        if all(
            getattr(self, field) is None
            for field in ("name", "description", "visibility", "color")
        ):
            raise ValueError("Provide at least one field to update.")
        return self
