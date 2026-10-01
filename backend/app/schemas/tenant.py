"""Tenant (organization) schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import APIModel, UTCDateTime


class TenantOut(APIModel):
    id: str
    name: str
    slug: str
    plan: str
    created_at: UTCDateTime


class TenantUpdateIn(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
