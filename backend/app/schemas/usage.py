"""Usage / analytics schemas (frontend contracts)."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import APIModel


class MetricPointOut(APIModel):
    date: str
    queries: int = 0
    successful: int = 0
    failed: int = 0
    tokens: int = 0
    latency_ms: int = 0
    storage_gb: float = 0.0


class StatCardOut(APIModel):
    value: int
    delta: int
    label: str


class StorageCardOut(APIModel):
    value: int
    quota: int
    label: str


class DashboardStatsOut(APIModel):
    documents: StatCardOut
    users: StatCardOut
    queries: StatCardOut
    storage: StorageCardOut


class RetrievalPerformanceOut(APIModel):
    avg_response_ms: int
    retrieval_accuracy: float
    citation_coverage: float
    failed_queries: int


class ActivityEventOut(APIModel):
    id: str
    actor: str
    action: str
    target: str
    timestamp: str
    type: Literal["upload", "invite", "api_key", "update", "query", "permission"]


class DashboardPayloadOut(APIModel):
    stats: DashboardStatsOut
    performance: RetrievalPerformanceOut
    activity: list[ActivityEventOut]
    series: list[MetricPointOut]


class ModelUsageOut(APIModel):
    model: str
    requests: int
    share: float


class UsageMetricsOut(APIModel):
    total_queries: int
    tokens_consumed: int
    average_latency_ms: int
    documents_processed: int
    storage_used_gb: float
    storage_quota_gb: float
    api_requests: int
    series: list[MetricPointOut]
    model_usage: list[ModelUsageOut]
