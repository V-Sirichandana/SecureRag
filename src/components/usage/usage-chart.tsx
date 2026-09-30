"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatCompactNumber, formatNumber } from "@/lib/utils";
import type { MetricPoint } from "@/lib/types";

function formatDateLabel(value: string) {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
}

type UsageTooltipProps = Pick<TooltipProps<number, string>, "active" | "payload" | "label">;

function UsageTooltip({ active, payload, label }: UsageTooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as MetricPoint | undefined;
  if (!point) return null;

  return (
    <div className="rounded-lg border bg-popover px-3 py-2.5 text-xs shadow-md">
      <p className="mb-2 font-medium">{formatDateLabel(String(label ?? point.date))}</p>
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[hsl(var(--chart-1))]" aria-hidden="true" />
          <span className="text-muted-foreground">Tokens</span>
          <span className="ml-auto font-medium tabular-nums">
            {formatCompactNumber(point.tokens)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[hsl(var(--chart-4))]" aria-hidden="true" />
          <span className="text-muted-foreground">Avg latency</span>
          <span className="ml-auto font-medium tabular-nums">
            {formatNumber(point.latencyMs)} ms
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[hsl(var(--chart-3))]" aria-hidden="true" />
          <span className="text-muted-foreground">Queries</span>
          <span className="ml-auto font-medium tabular-nums">
            {formatNumber(point.queries)}
          </span>
        </div>
      </div>
    </div>
  );
}

interface UsageChartProps {
  data: MetricPoint[];
}

export function UsageChart({ data }: UsageChartProps) {
  return (
    <Card className="gap-0 py-0 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div className="space-y-1.5">
          <CardTitle className="text-base font-semibold">Token consumption</CardTitle>
          <CardDescription>Tokens used per day with average response latency</CardDescription>
        </div>
        <Badge variant="outline" className="hidden text-muted-foreground sm:inline-flex">
          {data.length} days
        </Badge>
      </CardHeader>
      <CardContent>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
              <XAxis
                dataKey="date"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={28}
                tickFormatter={formatDateLabel}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              />
              <YAxis
                yAxisId="left"
                tickLine={false}
                axisLine={false}
                width={58}
                tickFormatter={(value: number) => formatCompactNumber(value)}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tickLine={false}
                axisLine={false}
                width={44}
                tickFormatter={(value: number) => `${value}`}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              />
              <Tooltip
                content={<UsageTooltip />}
                cursor={{ fill: "hsl(var(--muted))", fillOpacity: 0.55 }}
              />
              <Bar
                yAxisId="left"
                dataKey="tokens"
                fill="hsl(var(--chart-1))"
                fillOpacity={0.75}
                radius={[3, 3, 0, 0]}
                maxBarSize={26}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="latencyMs"
                stroke="hsl(var(--chart-4))"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4 border-t pt-4">
          <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
            <span className="h-2.5 w-2.5 rounded-sm bg-[hsl(var(--chart-1))]" aria-hidden="true" />
            Tokens used
          </span>
          <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
            <span className="h-0.5 w-4 rounded bg-[hsl(var(--chart-4))]" aria-hidden="true" />
            Average latency (ms)
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
