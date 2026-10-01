"""Analytics service — dashboard, usage and activity built from real data.

Metrics that require the RAG pipeline (retrieval accuracy, token usage from
model output) return zeros until that phase lands — nothing is fabricated.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Conversation, Message, Tenant
from app.repositories import AuditRepository, DocumentRepository, UserRepository
from app.schemas.usage import (
    ActivityEventOut,
    DashboardPayloadOut,
    DashboardStatsOut,
    MetricPointOut,
    ModelUsageOut,
    RetrievalPerformanceOut,
    StatCardOut,
    StorageCardOut,
    UsageMetricsOut,
)

GB = 1024**3
QUERY_ACTIONS = ("QUERY",)

ACTIVITY_TYPES: dict[str, str] = {
    "DOCUMENT_UPLOAD": "upload",
    "DOCUMENT_DELETE": "update",
    "DOCUMENT_UPDATE": "update",
    "USER_INVITED": "invite",
    "USER_REMOVED": "invite",
    "API_KEY_CREATED": "api_key",
    "API_KEY_REVOKED": "api_key",
    "PERMISSION_CHANGED": "permission",
    "QUERY": "query",
}


def _parse_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def _utc_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def range_bounds(
    range_key: str,
    custom_from: str | None = None,
    custom_to: str | None = None,
) -> tuple[date, date]:
    end = datetime.now(UTC).date()
    days = {"7d": 7, "30d": 30, "90d": 90}.get(range_key, 30)
    start = end - timedelta(days=days - 1)
    if custom_from:
        start = _parse_date(custom_from) or start
    if custom_to:
        end = _parse_date(custom_to) or end
    if start > end:
        start, end = end, start
    return start, end


def _iter_days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


class AnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit_repo = AuditRepository(db)
        self.document_repo = DocumentRepository(db)
        self.user_repo = UserRepository(db)

    # ------------------------------------------------------------- internals
    async def _query_events(self, tenant_id: uuid.UUID, start: date, end: date):
        since = _utc_midnight(start)
        until = _utc_midnight(end + timedelta(days=1))
        result = await self.db.execute(
            select(AuditLog.created_at, AuditLog.status).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action.in_(QUERY_ACTIONS),
                AuditLog.created_at >= since,
                AuditLog.created_at < until,
            )
        )
        return list(result.all())

    async def _series(
        self, tenant_id: uuid.UUID, start: date, end: date
    ) -> list[MetricPointOut]:
        events = await self._query_events(tenant_id, start, end)
        by_day: dict[date, dict[str, int]] = {
            day: {"queries": 0, "successful": 0, "failed": 0} for day in _iter_days(start, end)
        }
        for created_at, status in events:
            aware = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
            day = aware.date()
            if day in by_day:
                by_day[day]["queries"] += 1
                if status == "failure":
                    by_day[day]["failed"] += 1
                else:
                    by_day[day]["successful"] += 1
        return [
            MetricPointOut(
                date=day.isoformat(),
                queries=stats["queries"],
                successful=stats["successful"],
                failed=stats["failed"],
                tokens=0,
                latency_ms=0,
                storage_gb=0.0,
            )
            for day, stats in by_day.items()
        ]

    async def _chat_stats(self, tenant_id: uuid.UUID) -> tuple[int, int, int, int]:
        """(avg_latency_ms, assistant_count, cited_count, token_sum)."""
        result = await self.db.execute(
            select(
                func.avg(Message.latency_ms),
                func.count(Message.id),
                func.coalesce(
                    func.sum(case((Message.citations.is_not(None), 1), else_=0)),
                    0,
                ),
                func.coalesce(func.sum(Message.token_count), 0),
            )
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.tenant_id == tenant_id, Message.role == "assistant")
        )
        row = result.one()
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0), int(row[3] or 0)

    async def _model_usage(self, tenant_id: uuid.UUID) -> list[ModelUsageOut]:
        result = await self.db.execute(
            select(Message.model, func.count(Message.id))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.tenant_id == tenant_id,
                Message.role == "assistant",
                Message.model.is_not(None),
            )
            .group_by(Message.model)
        )
        rows = [(model or "unknown", int(count)) for model, count in result.all()]
        total = sum(count for _, count in rows)
        if total == 0:
            return []
        return [
            ModelUsageOut(model=model, requests=count, share=round(count * 100 / total, 1))
            for model, count in sorted(rows, key=lambda item: -item[1])
        ]

    async def _failed_queries(self, tenant_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action.in_(QUERY_ACTIONS),
                AuditLog.status == "failure",
            )
        )
        return int(result.scalar_one())

    @staticmethod
    def _delta(current: int, previous: int) -> int:
        if previous <= 0:
            return 0
        return round((current - previous) / previous * 100)

    # ------------------------------------------------------------ public API
    async def dashboard(self, *, tenant: Tenant) -> DashboardPayloadOut:
        now = datetime.now(UTC)
        week_start = (now - timedelta(days=6)).date()
        prior_week_start = week_start - timedelta(days=7)

        documents_total = await self.document_repo.count(tenant.id)
        documents_week = await self.document_repo.count(tenant.id, since=_utc_midnight(week_start))
        documents_before_week = await self.document_repo.count(
            tenant.id, since=_utc_midnight(prior_week_start)
        )

        members_total = await self.user_repo.member_count(tenant.id)
        queries_total = await self.audit_repo.count_actions(tenant.id, actions=QUERY_ACTIONS)
        queries_week = await self.audit_repo.count_actions(
            tenant.id, actions=QUERY_ACTIONS, since=_utc_midnight(week_start)
        )
        queries_before_week = await self.audit_repo.count_actions(
            tenant.id, actions=QUERY_ACTIONS, since=_utc_midnight(prior_week_start)
        )
        failed_queries = await self._failed_queries(tenant.id)

        storage_bytes = await self.document_repo.total_size(tenant.id)
        storage_gb = round(storage_bytes / GB, 2)

        series = await self._series(tenant.id, week_start, now.date())

        audit_rows, _ = await self.audit_repo.list(tenant.id, limit=8)
        activity = [
            ActivityEventOut(
                id=str(entry.id),
                actor=actor.name if actor else "System",
                action=entry.action,
                target=entry.resource_label or entry.resource_type or "",
                timestamp=entry.created_at.isoformat(),
                type=ACTIVITY_TYPES.get(entry.action, "update"),  # type: ignore[arg-type]
            )
            for entry, actor in audit_rows
        ]

        avg_latency, assistant_count, cited_count, _ = await self._chat_stats(tenant.id)
        citation_coverage = (
            round(cited_count / assistant_count * 100, 1) if assistant_count else 0.0
        )

        return DashboardPayloadOut(
            stats=DashboardStatsOut(
                documents=StatCardOut(
                    value=documents_total,
                    delta=self._delta(documents_week, documents_before_week - documents_week),
                    label="Documents",
                ),
                users=StatCardOut(value=members_total, delta=0, label="Members"),
                queries=StatCardOut(
                    value=queries_total,
                    delta=self._delta(queries_week, queries_before_week - queries_week),
                    label="Queries",
                ),
                storage=StorageCardOut(value=storage_gb, quota=10.0, label="Storage"),
            ),
            performance=RetrievalPerformanceOut(
                avg_response_ms=avg_latency,
                retrieval_accuracy=0.0,  # needs the RAG evaluation harness
                citation_coverage=citation_coverage,
                failed_queries=failed_queries,
            ),
            activity=activity,
            series=series,
        )

    async def usage(
        self,
        *,
        tenant: Tenant,
        range_key: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> UsageMetricsOut:
        start, end = range_bounds(range_key, date_from, date_to)
        series = await self._series(tenant.id, start, end)
        total_queries = sum(point.queries for point in series)

        documents_processed = await self.document_repo.count(
            tenant.id, since=_utc_midnight(start)
        )
        storage_bytes = await self.document_repo.total_size(tenant.id)
        avg_latency, _, _, token_sum = await self._chat_stats(tenant.id)

        return UsageMetricsOut(
            total_queries=total_queries,
            tokens_consumed=int(token_sum),
            average_latency_ms=avg_latency,
            documents_processed=documents_processed,
            storage_used_gb=round(storage_bytes / GB, 2),
            storage_quota_gb=10.0,
            api_requests=total_queries,
            series=series,
            model_usage=await self._model_usage(tenant.id),
        )

    async def activity_series(
        self,
        *,
        tenant: Tenant,
        range_key: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[MetricPointOut]:
        start, end = range_bounds(range_key, date_from, date_to)
        return await self._series(tenant.id, start, end)
