"use client";

import { BadgeCheck, CircleAlert, CircleDashed, CircleCheck } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { securityOverview } from "@/lib/mock/settings";
import type { SecurityStatusItem } from "@/lib/types";

const statusConfig: Record<
  SecurityStatusItem["status"],
  { label: string; className: string; tone: string; Icon: typeof CircleCheck }
> = {
  active: {
    label: "Active",
    className: "border-success/30 bg-success/10 text-success",
    tone: "text-success",
    Icon: CircleCheck,
  },
  attention: {
    label: "Attention",
    className: "border-warning/30 bg-warning/10 text-warning",
    tone: "text-warning",
    Icon: CircleAlert,
  },
  inactive: {
    label: "Inactive",
    className: "border-border bg-muted text-muted-foreground",
    tone: "text-muted-foreground",
    Icon: CircleDashed,
  },
};

export function SecurityOverview() {
  const attention = securityOverview.filter((item) => item.status === "attention").length;

  return (
    <Card className="gap-0 py-0 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div className="space-y-1.5">
          <CardTitle className="flex items-center gap-2 text-base font-semibold">
            <BadgeCheck className="h-4.5 w-4.5 text-primary" />
            Security Overview
          </CardTitle>
          <CardDescription>
            Posture of the controls that protect tenant data in this workspace
          </CardDescription>
        </div>
        <Badge
          variant="outline"
          className={cn(
            attention
              ? "border-warning/30 bg-warning/10 text-warning"
              : "border-success/30 bg-success/10 text-success",
          )}
        >
          {attention ? `${attention} need attention` : "All controls healthy"}
        </Badge>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {securityOverview.map((item) => {
            const config = statusConfig[item.status];
            return (
              <li
                key={item.label}
                className="flex items-start gap-3 rounded-lg border bg-muted/20 p-3.5"
              >
                <span
                  className={cn(
                    "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                    config.className,
                  )}
                >
                  <config.Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">{item.label}</p>
                    {item.demo ? (
                      <Badge
                        variant="outline"
                        className="border-dashed text-[10px] text-muted-foreground"
                      >
                        Demo data
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{item.detail}</p>
                  <p
                    className={cn(
                      "mt-1.5 text-[11px] font-semibold uppercase tracking-wide",
                      config.tone,
                    )}
                  >
                    {config.label}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
