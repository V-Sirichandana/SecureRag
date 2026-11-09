"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatNumber, formatPercent } from "@/lib/utils";

const colors = [
  "hsl(var(--chart-1))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-5))",
];

interface ModelUsageProps {
  data: { model: string; requests: number; share: number }[];
}

export function ModelUsage({ data }: ModelUsageProps) {
  return (
    <Card className="gap-0 py-0 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div className="space-y-1.5">
          <CardTitle className="text-base font-semibold">Model distribution</CardTitle>
          <CardDescription>Share of inference requests by model</CardDescription>
        </div>
        <Badge variant="outline" className="text-muted-foreground">
          {formatNumber(data.reduce((sum, item) => sum + item.requests, 0))} requests
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Tooltip
                cursor={false}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const entry = payload[0];
                  const item = entry.payload as { model: string; requests: number; share: number };
                  return (
                    <div className="rounded-lg border bg-popover px-3 py-2.5 text-xs shadow-md">
                      <p className="font-medium">{item.model}</p>
                      <p className="mt-1 text-muted-foreground">
                        {formatNumber(item.requests)} requests · {formatPercent(item.share)}
                      </p>
                    </div>
                  );
                }}
              />
              <Pie
                data={data}
                dataKey="share"
                nameKey="model"
                innerRadius={54}
                outerRadius={78}
                paddingAngle={2}
                strokeWidth={0}
              >
                {data.map((_, index) => (
                  <Cell key={index} fill={colors[index % colors.length]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>

        <ul className="space-y-2.5 border-t pt-4">
          {data.map((item, index) => (
            <li key={item.model} className="flex items-center gap-3 text-sm">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: colors[index % colors.length] }}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1 truncate font-mono text-xs">{item.model}</span>
              <span className="tabular-nums text-muted-foreground">
                {formatNumber(item.requests)}
              </span>
              <span className="w-10 text-right font-medium tabular-nums">
                {formatPercent(item.share)}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
