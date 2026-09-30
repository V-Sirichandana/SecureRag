"use client";

import * as React from "react";
import { toast } from "sonner";
import { ScrollText, Search, ShieldCheck, XCircle } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { AuditTable } from "@/components/security/audit-table";
import { useAuditLogs } from "@/lib/queries";
import { auditActions } from "@/lib/mock/audit";
import { useDebounce } from "@/hooks/use-client";
import { formatDateTime, formatTime } from "@/lib/utils";
import type { AuditAction, AuditEvent } from "@/lib/types";

export default function AuditLogsPage() {
  const [user, setUser] = React.useState("");
  const [action, setAction] = React.useState<"all" | AuditAction>("all");
  const [resource, setResource] = React.useState("");
  const [status, setStatus] = React.useState<"all" | "success" | "failure">("all");
  const [range, setRange] = React.useState("any");
  const [selected, setSelected] = React.useState<AuditEvent | null>(null);

  const debouncedUser = useDebounce(user, 250);
  const debouncedResource = useDebounce(resource, 250);

  const logs = useAuditLogs({
    user: debouncedUser || undefined,
    action,
    resource: debouncedResource || undefined,
    status,
  });

  const applyRange = (events: AuditEvent[]) => {
    if (range === "any") return events;
    const windowMs = range === "24h" ? 86_400_000 : range === "7d" ? 7 * 86_400_000 : 30 * 86_400_000;
    const cutoff = Date.now() - windowMs;
    return events.filter((event) => new Date(event.timestamp).getTime() >= cutoff);
  };

  const events = applyRange(logs.data ?? []);
  const failures = (logs.data ?? []).filter((event) => event.status === "failure").length;

  const clearFilters = () => {
    setUser("");
    setAction("all");
    setResource("");
    setStatus("all");
    setRange("any");
  };

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Audit Logs"
        description="A tamper-evident record of every security-relevant action in your organization."
        actions={
          <Button
            variant="outline"
            onClick={() => toast.success("Audit export queued. You'll receive an email.")}
          >
            Export CSV
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-success" />
          Logging active
        </Badge>
        <Badge variant="outline" className="text-muted-foreground">
          {(logs.data ?? []).length} events
        </Badge>
        {failures > 0 ? (
          <Badge variant="outline" className="gap-1.5 border-destructive/30 text-destructive">
            <XCircle className="h-3.5 w-3.5" />
            {failures} failed
          </Badge>
        ) : null}
      </div>

      <div className="grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">User</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={user}
              onChange={(event) => setUser(event.target.value)}
              placeholder="Name or email"
              className="pl-9"
              aria-label="Filter by user"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Action</Label>
          <Select value={action} onValueChange={(value) => setAction(value as typeof action)}>
            <SelectTrigger aria-label="Filter by action">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All actions</SelectItem>
              {auditActions.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Resource</Label>
          <Input
            value={resource}
            onChange={(event) => setResource(event.target.value)}
            placeholder="Document or target"
            aria-label="Filter by resource"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Status</Label>
          <Select value={status} onValueChange={(value) => setStatus(value as typeof status)}>
            <SelectTrigger aria-label="Filter by status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any status</SelectItem>
              <SelectItem value="success">Success</SelectItem>
              <SelectItem value="failure">Failure</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Date</Label>
          <Select value={range} onValueChange={setRange}>
            <SelectTrigger aria-label="Filter by date">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any time</SelectItem>
              <SelectItem value="24h">Last 24 hours</SelectItem>
              <SelectItem value="7d">Last 7 days</SelectItem>
              <SelectItem value="30d">Last 30 days</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card className="overflow-hidden py-0">
        {logs.isError ? (
          <div className="p-6">
            <ErrorState
              title="We couldn't load audit logs"
              description="The audit service didn't respond."
              onRetry={() => void logs.refetch()}
            />
          </div>
        ) : (
          <AuditTable
            events={events}
            isPending={logs.isPending}
            onSelect={setSelected}
            emptyState={
              <div className="p-6">
                <EmptyState
                  icon={ScrollText}
                  title="No matching events"
                  description="No audit entries match the current filters. Try widening the date range or clearing the search."
                  action={
                    <Button variant="outline" onClick={clearFilters}>
                      Clear filters
                    </Button>
                  }
                />
              </div>
            }
          />
        )}
      </Card>

      <Sheet open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle className="font-mono text-base">
              {selected?.action ?? "Event"}
            </SheetTitle>
            <SheetDescription>
              {selected ? formatDateTime(selected.timestamp) : ""}
            </SheetDescription>
          </SheetHeader>

          {selected ? (
            <div className="space-y-5 overflow-y-auto px-5 pb-6">
              <div className="flex items-center gap-2">
                <Badge
                  variant="outline"
                  className={
                    selected.status === "success"
                      ? "border-success/30 bg-success/10 text-success"
                      : "border-destructive/30 bg-destructive/10 text-destructive"
                  }
                >
                  {selected.status.toUpperCase()}
                </Badge>
                <Badge variant="outline" className="text-muted-foreground">
                  {selected.resourceType}
                </Badge>
              </div>

              <Section title="Actor">
                <Row label="Name" value={selected.user} />
                <Row label="Email" value={selected.userEmail} />
                <Row label="IP address" value={selected.ipAddress} mono />
              </Section>

              <Section title="Target">
                <Row label="Resource" value={selected.resource} />
                <Row label="Type" value={selected.resourceType} />
                <Row label="Occurred at" value={formatDateTime(selected.timestamp)} />
                <Row label="Time" value={formatTime(selected.timestamp)} mono />
              </Section>

              <Section title="Context">
                {Object.entries(selected.metadata).map(([key, value]) => (
                  <Row key={key} label={key} value={value} mono />
                ))}
                <Row label="User agent" value={selected.userAgent} />
              </Section>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      <div className="space-y-1.5 rounded-lg border bg-muted/30 p-3">{children}</div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 text-sm">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className={`break-all text-right ${mono ? "font-mono text-xs" : "font-medium"}`}>
        {value}
      </span>
    </div>
  );
}
