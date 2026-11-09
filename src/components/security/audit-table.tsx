"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { cn, formatDateTime, formatTime } from "@/lib/utils";
import type { AuditAction, AuditEvent } from "@/lib/types";

const actionTone: Record<AuditAction, string> = {
  LOGIN: "bg-chart-2/15 text-chart-2",
  LOGOUT: "bg-muted text-muted-foreground",
  DOCUMENT_UPLOAD: "bg-primary/10 text-primary",
  DOCUMENT_VIEW: "bg-muted text-muted-foreground",
  DOCUMENT_DELETE: "bg-destructive/10 text-destructive",
  QUERY: "bg-chart-3/15 text-chart-3",
  USER_INVITED: "bg-chart-5/15 text-chart-5",
  PERMISSION_CHANGED: "bg-warning/15 text-warning",
  API_KEY_CREATED: "bg-chart-1/15 text-chart-1",
};

interface AuditTableProps {
  events: AuditEvent[];
  isPending?: boolean;
  onSelect: (event: AuditEvent) => void;
  emptyState?: React.ReactNode;
}

export function AuditTable({ events, isPending, onSelect, emptyState }: AuditTableProps) {
  if (isPending) {
    return (
      <div className="space-y-3 p-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="flex animate-pulse items-center gap-4">
            <span className="h-4 w-16 rounded bg-muted" />
            <span className="h-4 w-32 rounded bg-muted" />
            <span className="h-4 flex-1 rounded bg-muted" />
            <span className="h-4 w-24 rounded bg-muted" />
          </div>
        ))}
      </div>
    );
  }

  if (events.length === 0) return <>{emptyState}</>;

  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-24">Timestamp</TableHead>
              <TableHead>User</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Resource</TableHead>
              <TableHead>IP address</TableHead>
              <TableHead className="text-right">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.map((event) => (
              <TableRow
                key={event.id}
                onClick={() => onSelect(event)}
                onKeyDown={(keyboardEvent) => {
                  if (keyboardEvent.key === "Enter") onSelect(event);
                }}
                tabIndex={0}
                className="cursor-pointer"
                aria-label={`Open details for ${event.action}`}
              >
                <TableCell className="whitespace-nowrap text-sm tabular-nums">
                  {formatTime(event.timestamp)}
                </TableCell>
                <TableCell>
                  <p className="text-sm font-medium">{event.user}</p>
                  <p className="text-xs text-muted-foreground">{event.userEmail}</p>
                </TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "inline-flex rounded-md px-2 py-1 font-mono text-[11px] font-medium",
                      actionTone[event.action],
                    )}
                  >
                    {event.action}
                  </span>
                </TableCell>
                <TableCell className="max-w-[220px] truncate text-sm text-muted-foreground">
                  {event.resource}
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm tabular-nums text-muted-foreground">
                  {event.ipAddress}
                </TableCell>
                <TableCell className="text-right">
                  <Badge
                    variant="outline"
                    className={cn(
                      "font-medium",
                      event.status === "success"
                        ? "border-success/30 bg-success/10 text-success"
                        : "border-destructive/30 bg-destructive/10 text-destructive",
                    )}
                  >
                    {event.status.toUpperCase()}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="divide-y md:hidden">
        {events.map((event) => (
          <button
            key={event.id}
            type="button"
            onClick={() => onSelect(event)}
            className="w-full p-4 text-left"
          >
            <div className="flex items-center justify-between gap-3">
              <span
                className={cn(
                  "inline-flex rounded-md px-2 py-1 font-mono text-[11px] font-medium",
                  actionTone[event.action],
                )}
              >
                {event.action}
              </span>
              <Badge
                variant="outline"
                className={cn(
                  event.status === "success"
                    ? "border-success/30 bg-success/10 text-success"
                    : "border-destructive/30 bg-destructive/10 text-destructive",
                )}
              >
                {event.status.toUpperCase()}
              </Badge>
            </div>
            <p className="mt-2 truncate text-sm font-medium">{event.resource}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {event.user} · {formatDateTime(event.timestamp)} · {event.ipAddress}
            </p>
          </button>
        ))}
      </div>
    </>
  );
}
