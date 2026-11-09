import type {
  ActivityEvent,
  DashboardStats,
  MetricPoint,
  RetrievalPerformance,
  TimeRange,
  UsageMetrics,
} from "@/lib/types";
import { dateOnly, iso, seeded } from "./utils";

function buildSeries(days: number): MetricPoint[] {
  const rand = seeded(days === 7 ? 42 : days === 30 ? 1337 : 9001);
  const points: MetricPoint[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const weekday = new Date(Date.now() - i * 86_400_000).getDay();
    const weekendDip = weekday === 0 || weekday === 6 ? 0.45 : 1;
    const base = 240 + rand() * 160;
    const queries = Math.round(base * weekendDip);
    const failed = Math.round(queries * (0.02 + rand() * 0.05));
    points.push({
      date: dateOnly(i),
      queries,
      successful: queries - failed,
      failed,
      tokens: Math.round(queries * (640 + rand() * 420)),
      latencyMs: Math.round(760 + rand() * 420),
      storageGb: Number((16.4 + (days - i) * 0.07 + rand() * 0.15).toFixed(2)),
    });
  }
  return points;
}

const seriesCache = new Map<TimeRange, MetricPoint[]>();

export function metricSeries(range: TimeRange): MetricPoint[] {
  const cached = seriesCache.get(range);
  if (cached) return cached;
  const days = range === "7d" ? 7 : range === "30d" ? 30 : 90;
  const series = buildSeries(days);
  seriesCache.set(range, series);
  return series;
}

export function dashboardStats(): DashboardStats {
  return {
    documents: { value: 1284, delta: 12.5, label: "Documents" },
    users: { value: 42, delta: 4, label: "Users" },
    queries: { value: 8923, delta: 18.2, label: "AI queries" },
    storage: { value: 18.4, quota: 50, label: "Storage" },
  };
}

export function retrievalPerformance(): RetrievalPerformance {
  return {
    avgResponseMs: 1240,
    retrievalAccuracy: 94.2,
    citationCoverage: 98.6,
    failedQueries: 37,
  };
}

export const recentActivity: ActivityEvent[] = [
  {
    id: "act_1",
    actor: "Vishvendra Vadla",
    action: "uploaded",
    target: "Employee Handbook.pdf",
    timestamp: iso({ minutes: 2 }),
    type: "upload",
  },
  {
    id: "act_2",
    actor: "Sarah Johnson",
    action: "invited",
    target: "John Doe to the workspace",
    timestamp: iso({ minutes: 12 }),
    type: "invite",
  },
  {
    id: "act_3",
    actor: "Alex Morgan",
    action: "created a new API key",
    target: "Production",
    timestamp: iso({ hours: 1 }),
    type: "api_key",
  },
  {
    id: "act_4",
    actor: "Daniel Smith",
    action: "updated",
    target: "Financial Report.pdf",
    timestamp: iso({ hours: 3 }),
    type: "update",
  },
  {
    id: "act_5",
    actor: "Priya Nair",
    action: "changed permissions on",
    target: "Security Policy.pdf",
    timestamp: iso({ hours: 6 }),
    type: "permission",
  },
  {
    id: "act_6",
    actor: "Marcus Webb",
    action: "asked 14 questions against",
    target: "Engineering",
    timestamp: iso({ hours: 9 }),
    type: "query",
  },
];

export function sliceSeries(
  series: MetricPoint[],
  from?: string,
  to?: string,
): MetricPoint[] {
  const start = from ? new Date(`${from}T00:00:00`).getTime() : null;
  const end = to ? new Date(`${to}T23:59:59`).getTime() : null;
  const sliced = series.filter((point) => {
    const time = new Date(`${point.date}T00:00:00`).getTime();
    if (start !== null && time < start) return false;
    if (end !== null && time > end) return false;
    return true;
  });
  return sliced.length > 0 ? sliced : series.slice(-7);
}

export function usageMetricsFor(series: MetricPoint[]): UsageMetrics {
  const totalQueries = series.reduce((sum, p) => sum + p.queries, 0);
  const tokens = series.reduce((sum, p) => sum + p.tokens, 0);
  const latency = Math.round(series.reduce((sum, p) => sum + p.latencyMs, 0) / series.length);

  return {
    totalQueries,
    tokensConsumed: tokens,
    averageLatencyMs: latency,
    documentsProcessed: Math.max(12, Math.round(totalQueries * 0.046)),
    storageUsedGb: series[series.length - 1].storageGb,
    storageQuotaGb: 50,
    apiRequests: Math.round(totalQueries * 0.34),
    series,
    modelUsage: [
      { model: "gpt-4o-mini", requests: Math.round(totalQueries * 0.58), share: 58 },
      { model: "gpt-4o", requests: Math.round(totalQueries * 0.24), share: 24 },
      { model: "claude-3-5-sonnet", requests: Math.round(totalQueries * 0.13), share: 13 },
      { model: "llama-3.1-70b", requests: Math.round(totalQueries * 0.05), share: 5 },
    ],
  };
}

export function usageMetrics(range: TimeRange): UsageMetrics {
  return usageMetricsFor(metricSeries(range));
}
