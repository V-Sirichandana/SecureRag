import { Activity, FileCheck2, Target, XCircle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DEMO_NOTICE } from "@/lib/mock/utils";
import { formatNumber } from "@/lib/utils";
import type { RetrievalPerformance } from "@/lib/types";

const metrics = [
  {
    key: "avgResponseMs" as const,
    label: "Average response time",
    icon: Activity,
    render: (value: number) => `${formatNumber(value)} ms`,
    tone: "text-primary",
  },
  {
    key: "retrievalAccuracy" as const,
    label: "Retrieval accuracy",
    icon: Target,
    render: (value: number) => `${value.toFixed(1)}%`,
    tone: "text-success",
  },
  {
    key: "citationCoverage" as const,
    label: "Citation coverage",
    icon: FileCheck2,
    render: (value: number) => `${value.toFixed(1)}%`,
    tone: "text-chart-3",
  },
  {
    key: "failedQueries" as const,
    label: "Failed queries",
    icon: XCircle,
    render: (value: number) => formatNumber(value),
    tone: "text-destructive",
  },
];

export function RetrievalPerformanceGrid({ data }: { data: RetrievalPerformance }) {
  return (
    <Card className="shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
      <CardHeader className="flex-row items-start justify-between space-y-0 gap-4">
        <div className="space-y-1.5">
          <CardTitle className="text-base font-semibold">Retrieval performance</CardTitle>
          <CardDescription>Quality signals from the last 7 days</CardDescription>
        </div>
        <Badge variant="outline" className="text-muted-foreground">
          {DEMO_NOTICE}
        </Badge>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        {metrics.map((metric) => (
          <div
            key={metric.key}
            className="flex items-center gap-3 rounded-lg border bg-muted/30 px-3.5 py-3"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-background">
              <metric.icon className={`h-4.5 w-4.5 ${metric.tone}`} />
            </span>
            <div className="min-w-0">
              <p className="truncate text-xs text-muted-foreground">{metric.label}</p>
              <p className="text-lg font-semibold tabular-nums">{metric.render(data[metric.key])}</p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
