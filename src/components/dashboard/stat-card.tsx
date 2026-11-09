import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn, formatNumber, formatPercent } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string;
  icon: LucideIcon;
  delta?: number;
  deltaLabel?: string;
  hint?: string;
  progress?: number;
  progressLabel?: string;
}

export function StatCard({
  label,
  value,
  icon: Icon,
  delta,
  deltaLabel,
  hint,
  progress,
  progressLabel,
}: StatCardProps) {
  const positive = (delta ?? 0) >= 0;

  return (
    <Card className="gap-0 py-5 shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition-shadow hover:shadow-md">
      <CardContent className="px-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {label}
            </p>
            <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
          </div>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="h-4.5 w-4.5" />
          </span>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          {typeof delta === "number" ? (
            <span
              className={cn(
                "inline-flex items-center gap-1 font-medium",
                positive ? "text-success" : "text-destructive",
              )}
            >
              {positive ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
              {formatPercent(delta)}
            </span>
          ) : null}
          {deltaLabel ? <span className="text-muted-foreground">{deltaLabel}</span> : null}
          {hint ? <span className="text-muted-foreground">{hint}</span> : null}
        </div>

        {typeof progress === "number" ? (
          <div className="mt-3 space-y-1.5">
            <Progress value={progress} className="h-1.5" aria-label={progressLabel} />
            <p className="text-xs text-muted-foreground">{progressLabel}</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function formatStatValue(value: number) {
  return formatNumber(value);
}
