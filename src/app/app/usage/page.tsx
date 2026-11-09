"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Activity,
  Coins,
  Download,
  FileText,
  HardDrive,
  PlugZap,
  Timer,
} from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatCard } from "@/components/dashboard/stat-card";
import { UsageChart } from "@/components/usage/usage-chart";
import { ModelUsage } from "@/components/usage/model-usage";
import { ErrorState } from "@/components/common/error-state";
import { ChartSkeleton } from "@/components/common/skeletons";
import { useUsage } from "@/lib/queries";
import { cn, formatDate, formatNumber, formatCompactNumber, formatPercent } from "@/lib/utils";
import type { TimeRange } from "@/lib/types";

type RangeChoice = TimeRange | "custom";

function isoDaysAgo(days: number): string {
  const date = new Date(Date.now() - days * 86_400_000);
  return date.toISOString().slice(0, 10);
}

export default function UsagePage() {
  const [choice, setChoice] = React.useState<RangeChoice>("7d");
  const [from, setFrom] = React.useState(isoDaysAgo(7));
  const [to, setTo] = React.useState(isoDaysAgo(0));

  const customValid =
    choice !== "custom" || (Boolean(from) && Boolean(to) && from <= to);

  const usage = useUsage(
    choice === "custom" ? "90d" : choice,
    choice === "custom" && customValid ? { from, to } : undefined,
  );

  const data = usage.data;

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Usage"
        description="Monitor consumption against your plan and spot anomalies before they become invoices."
        actions={
          <Button
            variant="outline"
            onClick={() => toast.success("Usage report queued. You'll receive an email.")}
          >
            <Download className="mr-2 h-4 w-4" />
            Export report
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-3">
        <Tabs
          value={choice}
          onValueChange={(value) => setChoice(value as RangeChoice)}
          aria-label="Usage time range"
        >
          <TabsList className="h-9">
            <TabsTrigger value="7d" className="text-xs">
              7 days
            </TabsTrigger>
            <TabsTrigger value="30d" className="text-xs">
              30 days
            </TabsTrigger>
            <TabsTrigger value="90d" className="text-xs">
              90 days
            </TabsTrigger>
            <TabsTrigger value="custom" className="text-xs">
              Custom
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {choice === "custom" ? (
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Label htmlFor="usage-from" className="text-xs text-muted-foreground">
                From
              </Label>
              <Input
                id="usage-from"
                type="date"
                value={from}
                max={to}
                onChange={(event) => setFrom(event.target.value)}
                className="h-9 w-40 text-sm"
              />
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor="usage-to" className="text-xs text-muted-foreground">
                To
              </Label>
              <Input
                id="usage-to"
                type="date"
                value={to}
                min={from}
                onChange={(event) => setTo(event.target.value)}
                className="h-9 w-40 text-sm"
              />
            </div>
            {!customValid ? (
              <p className="text-xs font-medium text-destructive" role="alert">
                The start date must be before the end date.
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="ml-auto flex items-center gap-2">
          <Badge variant="outline" className="text-muted-foreground">
            {choice === "custom"
              ? customValid
                ? `${formatDate(from)} – ${formatDate(to)}`
                : "Custom range"
              : choice === "7d"
                ? "Last 7 days"
                : choice === "30d"
                  ? "Last 30 days"
                  : "Last 90 days"}
          </Badge>
          <Badge variant="secondary" className="gap-1.5">
            Demo data
          </Badge>
        </div>
      </div>

      {usage.isError ? (
        <ErrorState
          title="We couldn't load usage metrics"
          description="The billing metrics endpoint did not respond."
          onRetry={() => void usage.refetch()}
        />
      ) : usage.isPending || !data ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="h-32 animate-pulse rounded-xl border bg-muted/40" />
            ))}
          </div>
          <ChartSkeleton className="h-96" />
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <StatCard
              label="AI queries"
              value={formatNumber(data.totalQueries)}
              icon={Activity}
              deltaLabel="in selected window"
            />
            <StatCard
              label="Tokens consumed"
              value={formatCompactNumber(data.tokensConsumed)}
              icon={Coins}
              deltaLabel="input + output"
            />
            <StatCard
              label="Average latency"
              value={`${formatNumber(data.averageLatencyMs)} ms`}
              icon={Timer}
              deltaLabel="retrieval + generation"
            />
            <StatCard
              label="API requests"
              value={formatNumber(data.apiRequests)}
              icon={PlugZap}
              deltaLabel="programmatic calls"
            />
            <StatCard
              label="Documents processed"
              value={formatNumber(data.documentsProcessed)}
              icon={FileText}
              deltaLabel="ingested + re-indexed"
            />
            <StatCard
              label="Storage used"
              value={`${data.storageUsedGb.toFixed(1)} GB`}
              icon={HardDrive}
              progress={Math.min(100, Math.round((data.storageUsedGb / data.storageQuotaGb) * 100))}
              progressLabel={`${data.storageUsedGb.toFixed(1)} GB of ${data.storageQuotaGb} GB quota`}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-5">
            <div className="lg:col-span-3">
              <UsageChart data={data.series} />
            </div>
            <div className="lg:col-span-2">
              <ModelUsage data={data.modelUsage} />
            </div>
          </div>

          <Card className="gap-0 py-0 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
              <div className="space-y-1">
                <p className="text-sm font-semibold">Daily breakdown</p>
                <p className="text-xs text-muted-foreground">
                  Every metric point in the selected window
                </p>
              </div>
              <Badge variant="outline" className="text-muted-foreground">
                {data.series.length} rows
              </Badge>
            </div>
            <div className="max-h-[420px] overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-background">
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Date</TableHead>
                    <TableHead className="text-right">Queries</TableHead>
                    <TableHead className="text-right">Failed</TableHead>
                    <TableHead className="text-right">Tokens</TableHead>
                    <TableHead className="text-right">Avg latency</TableHead>
                    <TableHead className="text-right">Storage</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...data.series].reverse().map((point) => (
                    <TableRow key={point.date}>
                      <TableCell className="whitespace-nowrap text-sm">
                        {formatDate(`${point.date}T00:00:00`)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatNumber(point.queries)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right tabular-nums",
                          point.failed > 20 && "text-destructive",
                        )}
                      >
                        {formatNumber(point.failed)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatCompactNumber(point.tokens)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatNumber(point.latencyMs)} ms
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {point.storageGb.toFixed(2)} GB
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>

          <p className="text-xs text-muted-foreground">
            Aggregates shown are illustrative demo data until the billing metrics service is
            connected. Quota alerts trigger at {formatPercent(80)} of your storage limit.
          </p>
        </>
      )}
    </div>
  );
}
