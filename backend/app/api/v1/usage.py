"""Usage / analytics routes (real data, honest zeros for RAG-only metrics)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentTenant, DbSession
from app.schemas.usage import DashboardPayloadOut, MetricPointOut, UsageMetricsOut
from app.services.analytics_service import AnalyticsService

usage_router = APIRouter(tags=["Usage"])


@usage_router.get(
    "/usage",
    response_model=UsageMetricsOut,
    summary="Usage summary for a time range",
)
async def usage_summary(
    tenant: CurrentTenant,
    db: DbSession,
    range_key: Annotated[str, Query(alias="range")] = "30d",
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
) -> UsageMetricsOut:
    return await AnalyticsService(db).usage(
        tenant=tenant, range_key=range_key, date_from=date_from, date_to=date_to
    )


@usage_router.get(
    "/analytics/usage",
    response_model=UsageMetricsOut,
    summary="Usage metrics (frontend contract)",
)
async def analytics_usage(
    tenant: CurrentTenant,
    db: DbSession,
    range_key: Annotated[str, Query(alias="range")] = "30d",
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
) -> UsageMetricsOut:
    return await AnalyticsService(db).usage(
        tenant=tenant, range_key=range_key, date_from=date_from, date_to=date_to
    )


@usage_router.get(
    "/analytics/activity",
    response_model=list[MetricPointOut],
    summary="Query activity series (frontend contract)",
)
async def analytics_activity(
    tenant: CurrentTenant,
    db: DbSession,
    range_key: Annotated[str, Query(alias="range")] = "7d",
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
) -> list[MetricPointOut]:
    return await AnalyticsService(db).activity_series(
        tenant=tenant, range_key=range_key, date_from=date_from, date_to=date_to
    )


@usage_router.get(
    "/analytics/dashboard",
    response_model=DashboardPayloadOut,
    summary="Dashboard payload (frontend contract)",
)
async def analytics_dashboard(
    tenant: CurrentTenant,
    db: DbSession,
) -> DashboardPayloadOut:
    return await AnalyticsService(db).dashboard(tenant=tenant)
