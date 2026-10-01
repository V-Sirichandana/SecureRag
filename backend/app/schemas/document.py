"""Document schemas (frontend DocumentRecord contract)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import APIModel, UTCDateTime

ClassificationLiteral = Literal["public", "internal", "confidential", "restricted"]
StatusLiteral = Literal["processing", "ready", "failed", "archived"]


class DocumentOut(APIModel):
    id: str
    name: str
    file_type: str
    size_bytes: int
    collection_id: str | None = None
    collection_name: str = "Unfiled"
    owner: str = ""
    department: str = "General"
    classification: ClassificationLiteral
    status: StatusLiteral
    created_at: UTCDateTime
    updated_at: UTCDateTime
    page_count: int = 0
    chunk_count: int = 0
    tags: list[str] = []


class DocumentCreateIn(APIModel):
    name: str = Field(min_length=1, max_length=400)
    # frontend sends collectionId
    collection_id: str
    classification: ClassificationLiteral = "internal"
    # optional metadata (frontend currently sends only the fields above)
    file_type: str | None = Field(default=None, max_length=16)
    size_bytes: int | None = Field(default=None, ge=0)
    page_count: int | None = Field(default=None, ge=0)


class DocumentUpdateIn(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=400)
    classification: ClassificationLiteral | None = None
    status: StatusLiteral | None = None
    collection_id: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> DocumentUpdateIn:
        if all(
            getattr(self, field) is None
            for field in ("name", "classification", "status", "collection_id")
        ):
            raise ValueError("Provide at least one field to update.")
        return self


class DocumentPermissionsIn(APIModel):
    scope: Literal["everyone", "members", "roles", "users"]
    targets: list[str] = []


class DocumentPermissionsOut(APIModel):
    id: str
    scope: str
    targets: list[str] = []


class DocumentParagraphOut(APIModel):
    id: str
    text: str
    highlight: str | None = None


class DocumentPageOut(APIModel):
    page_number: int
    title: str
    paragraphs: list[DocumentParagraphOut] = []
