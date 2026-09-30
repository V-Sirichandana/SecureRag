import { CheckCircle2, Clock3, CircleSlash, Loader2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Classification, DocumentStatus, UserStatus } from "@/lib/types";

const documentStatus: Record<
  DocumentStatus,
  { label: string; className: string; icon: React.ComponentType<{ className?: string }> }
> = {
  processing: {
    label: "Processing",
    className: "border-warning/30 bg-warning/10 text-warning",
    icon: Loader2,
  },
  ready: {
    label: "Ready",
    className: "border-success/30 bg-success/10 text-success",
    icon: CheckCircle2,
  },
  failed: {
    label: "Failed",
    className: "border-destructive/30 bg-destructive/10 text-destructive",
    icon: XCircle,
  },
  archived: {
    label: "Archived",
    className: "border-border bg-muted text-muted-foreground",
    icon: CircleSlash,
  },
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const config = documentStatus[status];
  const Icon = config.icon;
  return (
    <Badge variant="outline" className={cn("gap-1.5 font-medium", config.className)}>
      <Icon className={cn("h-3 w-3", status === "processing" && "animate-spin")} />
      {config.label}
    </Badge>
  );
}

const userStatus: Record<UserStatus, { label: string; className: string }> = {
  active: { label: "Active", className: "border-success/30 bg-success/10 text-success" },
  invited: { label: "Invited", className: "border-primary/30 bg-primary/10 text-primary" },
  disabled: { label: "Disabled", className: "border-border bg-muted text-muted-foreground" },
};

export function UserStatusBadge({ status }: { status: UserStatus }) {
  const config = userStatus[status];
  return (
    <Badge variant="outline" className={cn("font-medium", config.className)}>
      {config.label}
    </Badge>
  );
}

const classificationStyles: Record<Classification, string> = {
  public: "border-success/30 bg-success/10 text-success",
  internal: "border-primary/30 bg-primary/10 text-primary",
  confidential: "border-warning/30 bg-warning/10 text-warning",
  restricted: "border-destructive/30 bg-destructive/10 text-destructive",
};

export function ClassificationBadge({ value }: { value: Classification }) {
  return (
    <Badge variant="outline" className={cn("font-medium capitalize", classificationStyles[value])}>
      {value}
    </Badge>
  );
}

export function TimeBadge({ label }: { label: string }) {
  return (
    <Badge variant="outline" className="gap-1.5 font-medium">
      <Clock3 className="h-3 w-3" />
      {label}
    </Badge>
  );
}
