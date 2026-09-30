"use client";

import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { useActivitySeries } from "@/lib/queries";
import { ChartSkeleton } from "@/components/common/skeletons";
import { ErrorState } from "@/components/common/error-state";
import { formatNumber } from "@/lib/utils";
import type { MetricPoint, TimeRange } from "@/lib/types";

const seriesMeta = [
  { key: "queries", label: "Queries", color: "hsl(var(--chart-1))" },
  { key: "successful", label: "Successful responses", color: "hsl(var(--chart-3))" },
  { key: "failed", label: "Failed responses", color: "hsl(var(--destructive))" },
] as const;

function formatDateLabel(value: string) {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
}

type ChartTooltipProps = Pick<TooltipProps<number, string>, "active" | "payload" | "label">;

function ChartTooltip({ active, payload, label }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as MetricPoint | undefined;
  if (!point) return null;

  return (
    <div className="rounded-lg border bg-popover px-3 py-2.5 text-xs shadow-md">
      <p className="mb-2 font-medium">{formatDateLabel(String(label ?? point.date))}</p>
      <div className="space-y-1.5">
        {seriesMeta.map((meta) => (
          <div key={meta.key} className="flex items-center gap-2">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: meta.color }}
              aria-hidden="true"
            />
            <span className="text-muted-foreground">{meta.label}</span>
            <span className="ml-auto font-medium tabular-nums">
              {formatNumber(point[meta.key] as number)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function QueryActivityChart() {
  const [range, setRange] = useState<TimeRange>("7d");
  const { data, isPending, isError, refetch } = useActivitySeries(range);

  return (
    <Card className="col-span-full shadow-[0_1px_2px_rgba(0,0,0,0.03)] xl:col-span-2">
      <CardHeader className="flex-row items-start justify-between space-y-0 gap-4">
        <div className="space-y-1.5">
          <CardTitle className="text-base font-semibold">Query activity</CardTitle>
          <CardDescription>
            Volume and outcome of AI queries against your knowledge base
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="hidden text-muted-foreground sm:inline-flex">
            Demo data
          </Badge>
          <Tabs value={range} onValueChange={(value) => setRange(value as TimeRange)}>
            <TabsList className="h-8">
              <TabsTrigger value="7d" className="text-xs">
                7 days
              </TabsTrigger>
              <TabsTrigger value="30d" className="text-xs">
                30 days
              </TabsTrigger>
              <TabsTrigger value="90d" className="text-xs">
                90 days
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </CardHeader>
      <CardContent>
        {isPending ? <ChartSkeleton className="-mx-2 p-0" /> : null}
        {isError ? (
          <ErrorState
            title="We couldn't load query activity"
            description="The analytics endpoint did not respond."
            onRetry={() => void refetch()}
            className="border-0 py-10"
          />
        ) : null}
        {data ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                <defs>
                  <linearGradient id="fillQueries" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.32} />
                    <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="fillFailed" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--destructive))" stopOpacity={0.24} />
                    <stop offset="100%" stopColor="hsl(var(--destructive))" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
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
                  tickLine={false}
                  axisLine={false}
                  width={46}
                  tickFormatter={(value: number) => formatNumber(value)}
                  tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                />
                <Tooltip
                  content={<ChartTooltip />}
                  cursor={{ stroke: "hsl(var(--border))", strokeWidth: 1 }}
                />
                <Area
                  type="monotone"
                  dataKey="queries"
                  stroke="hsl(var(--chart-1))"
                  strokeWidth={2}
                  fill="url(#fillQueries)"
                />
                <Area
                  type="monotone"
                  dataKey="successful"
                  stroke="hsl(var(--chart-3))"
                  strokeWidth={1.75}
                  fill="none"
                />
                <Area
                  type="monotone"
                  dataKey="failed"
                  stroke="hsl(var(--destructive))"
                  strokeWidth={1.75}
                  fill="url(#fillFailed)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-4 border-t pt-4">
          {seriesMeta.map((meta) => (
            <span key={meta.key} className="inline-flex items-center gap-2 text-xs text-muted-foreground">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: meta.color }}
                aria-hidden="true"
              />
              {meta.label}
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
