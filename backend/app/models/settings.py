"""Per-tenant settings (frontend settings screens)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPk


class TenantSettings(Base, UUIDPk, TimestampMixin):
    """One row per (tenant, section) holding a JSON settings blob."""

    __tablename__ = "tenant_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "section", name="uq_tenant_settings_section"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    section: Mapped[str] = mapped_column(String(32), nullable=False)  # general | security | ...
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
