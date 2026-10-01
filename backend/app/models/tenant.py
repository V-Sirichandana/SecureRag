"""Tenant (organization) model."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPk


class Tenant(Base, UUIDPk, TimestampMixin):
    """An isolated organization. Every tenant-owned row carries ``tenant_id``."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True, nullable=False)
    # frontend compatibility: plan tier shown in the organization switcher
    plan: Mapped[str] = mapped_column(String(32), default="Free", nullable=False)
