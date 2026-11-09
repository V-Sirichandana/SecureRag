"""Shared schema building blocks.

All response models serialize to camelCase (the frontend's convention) while
accepting snake_case or camelCase on input.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

RoleLiteral = Literal["owner", "admin", "manager", "member", "viewer"]
StatusLiteral = Literal["active", "invited", "disabled"]


def to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


UTCDateTime = Annotated[
    datetime,
    AfterValidator(_ensure_utc),
    PlainSerializer(lambda value: value.isoformat(), return_type=str),
]


def _lower_role(value: str) -> str:
    return value.strip().lower()


# role accepts any case on input, always emits lowercase (frontend contract)
RoleField = Annotated[RoleLiteral, AfterValidator(_lower_role)]


class APIModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class OkResponse(APIModel):
    ok: bool = True


class PaginationMeta(APIModel):
    total: int = Field(description="Total number of matching records")
    page: int = 1
    page_size: int = 50
