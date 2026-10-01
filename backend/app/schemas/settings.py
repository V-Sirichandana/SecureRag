"""Settings schemas (frontend contracts) and search results."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel


class SettingsGeneral(APIModel):
    organization_name: str = ""
    description: str = ""
    default_collection_id: str | None = None
    support_email: str = ""


class SettingsSecurity(APIModel):
    mfa_required: bool = False
    session_timeout_minutes: int = Field(default=60, ge=5)
    min_password_length: int = Field(default=8, ge=8)
    require_uppercase: bool = False
    require_number: bool = False
    sso_enabled: bool = False
    sso_provider: str = ""
    ip_allowlist_enabled: bool = False
    ip_allowlist: list[str] = []


class SettingsAI(APIModel):
    default_model: str = "gpt-4o-mini"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_response_tokens: int = Field(default=1024, ge=1)
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    reranking_enabled: bool = True
    require_citations: bool = True


class SettingsNotifications(APIModel):
    security_alerts: bool = True
    member_joined_alerts: bool = True
    document_processing_alerts: bool = True
    usage_threshold_alerts: bool = True
    weekly_digest: bool = True
    product_updates: bool = False


class SettingsBilling(APIModel):
    plan_name: str = "Free"
    plan_price: str = "$0"
    seats_used: int = 0
    seats_total: int = 5
    storage_used_gb: float = 0.0
    storage_total_gb: float = 10.0
    renews_at: str = ""
    billing_email: str = ""
    auto_renew: bool = True
    invoice_delivery: Literal["email", "portal"] = "email"
    purchase_order_number: str = ""


class InvoiceOut(APIModel):
    id: str
    number: str
    issued_at: str
    amount: str
    status: Literal["paid", "open", "refunded"] = "paid"


class SearchResultOut(APIModel):
    id: str
    title: str
    subtitle: str
    type: Literal["document", "user", "collection", "setting", "page"]
    href: str
