import { USE_MOCKS, request } from "./client";
import { auditLogs as mockAudit, auditActions } from "@/lib/mock/audit";
import { apiKeys as mockKeys } from "@/lib/mock/settings";
import {
  dashboardStats,
  metricSeries,
  recentActivity,
  retrievalPerformance,
  sliceSeries,
  usageMetrics,
  usageMetricsFor,
} from "@/lib/mock/analytics";
import { latency } from "@/lib/mock/utils";
import type {
  ActivityEvent,
  ApiKey,
  AuditAction,
  AuditEvent,
  DashboardStats,
  MetricPoint,
  RetrievalPerformance,
  TimeRange,
  UsageMetrics,
} from "@/lib/types";

export interface DashboardPayload {
  stats: DashboardStats;
  performance: RetrievalPerformance;
  activity: ActivityEvent[];
  series: MetricPoint[];
}

export async function getDashboardStats(): Promise<DashboardPayload> {
  if (USE_MOCKS) {
    await latency(400, 800);
    return {
      stats: dashboardStats(),
      performance: retrievalPerformance(),
      activity: recentActivity,
      series: metricSeries("7d"),
    };
  }
  return request<DashboardPayload>("/analytics/dashboard");
}

export interface UsageWindow {
  from?: string;
  to?: string;
}

export async function getUsage(
  range: TimeRange,
  custom?: UsageWindow,
): Promise<UsageMetrics> {
  if (USE_MOCKS) {
    await latency(450, 900);
    if (custom?.from || custom?.to) {
      return usageMetricsFor(sliceSeries(metricSeries("90d"), custom.from, custom.to));
    }
    return usageMetrics(range);
  }
  const params = new URLSearchParams({ range });
  if (custom?.from) params.set("from", custom.from);
  if (custom?.to) params.set("to", custom.to);
  return request<UsageMetrics>(`/analytics/usage?${params.toString()}`);
}

export async function getActivitySeries(range: TimeRange): Promise<MetricPoint[]> {
  if (USE_MOCKS) {
    await latency(350, 700);
    return metricSeries(range);
  }
  return request<MetricPoint[]>(`/analytics/activity?range=${range}`);
}

export interface AuditFilters {
  user?: string;
  action?: AuditAction | "all";
  resource?: string;
  status?: "all" | "success" | "failure";
}

export async function getAuditLogs(filters: AuditFilters = {}): Promise<AuditEvent[]> {
  if (USE_MOCKS) {
    await latency();
    const user = filters.user?.toLowerCase();
    const resource = filters.resource?.toLowerCase();
    return mockAudit.filter((event) => {
      if (user && !event.user.toLowerCase().includes(user) && !event.userEmail.toLowerCase().includes(user)) {
        return false;
      }
      if (filters.action && filters.action !== "all" && event.action !== filters.action) return false;
      if (filters.status && filters.status !== "all" && event.status !== filters.status) return false;
      if (resource && !event.resource.toLowerCase().includes(resource)) return false;
      return true;
    });
  }
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value && value !== "all") params.set(key, String(value));
  });
  return request<AuditEvent[]>(`/audit?${params.toString()}`);
}

export { auditActions };

export async function getApiKeys(): Promise<ApiKey[]> {
  if (USE_MOCKS) {
    await latency(350, 700);
    return [...mockKeys];
  }
  return request<ApiKey[]>("/api-keys");
}

export interface CreateApiKeyPayload {
  name: string;
  environment: "live" | "test";
  expiration: "never" | "30" | "90" | "365";
  permissions: string[];
}

export async function createApiKey(
  payload: CreateApiKeyPayload,
): Promise<{ key: ApiKey; plaintext: string }> {
  if (USE_MOCKS) {
    await latency(700, 1200);
    const prefix = payload.environment === "live" ? "sk_live_" : "sk_test_";
    const plaintext = `${prefix}${Math.random().toString(36).slice(2, 10)}${Math.random()
      .toString(36)
      .slice(2, 10)}${Math.random().toString(36).slice(2, 14)}`;
    const days = payload.expiration === "never" ? null : Number(payload.expiration);
    const key: ApiKey = {
      id: `key_${Math.random().toString(36).slice(2, 8)}`,
      name: payload.name,
      environment: payload.environment,
      maskedKey: `${prefix}${"•".repeat(16)}`,
      createdAt: new Date().toISOString(),
      lastUsedAt: null,
      expiresAt: days ? new Date(Date.now() + days * 86_400_000).toISOString() : null,
      permissions: payload.permissions,
    };
    mockKeys.unshift(key);
    return { key, plaintext };
  }
  return request(`/api-keys`, { method: "POST", body: payload });
}

export async function revokeApiKey(id: string): Promise<void> {
  if (USE_MOCKS) {
    await latency(300, 600);
    const index = mockKeys.findIndex((item) => item.id === id);
    if (index >= 0) mockKeys.splice(index, 1);
    return;
  }
  await request(`/api-keys/${id}`, { method: "DELETE" });
}
