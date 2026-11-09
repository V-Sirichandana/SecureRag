"""Audit event schemas (frontend AuditEvent contract)."""

from __future__ import annotations

from typing import Any, Literal

from app.schemas.common import APIModel, UTCDateTime


class AuditEventOut(APIModel):
    id: str
    timestamp: UTCDateTime
    user: str
    user_email: str
    action: str
    resource: str
    resource_type: str
    ip_address: str
    status: Literal["success", "failure"] = "success"
    user_agent: str = ""
    metadata: dict[str, Any] = {}
