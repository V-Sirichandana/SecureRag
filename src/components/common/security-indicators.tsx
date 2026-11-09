import { CheckCircle2, Lock, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

export function SecureConnectionBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border bg-muted/50 px-2.5 py-1 text-[11px] font-medium text-muted-foreground",
        className,
      )}
    >
      <Lock className="h-3 w-3 text-success" />
      Secure connection
    </span>
  );
}

export function AccessControlledBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border bg-muted/50 px-2.5 py-1 text-[11px] font-medium text-muted-foreground",
        className,
      )}
    >
      <ShieldCheck className="h-3 w-3 text-success" />
      Access controlled
    </span>
  );
}

export function SecurityIndicator({
  label,
  className,
}: {
  label: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border bg-card px-2.5 py-1.5 text-xs font-medium text-muted-foreground",
        className,
      )}
    >
      <CheckCircle2 className="h-3.5 w-3.5 text-success" />
      {label}
    </span>
  );
}
