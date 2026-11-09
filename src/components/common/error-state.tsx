import { AlertTriangle, FileQuestion, Lock, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  description: string;
  onRetry?: () => void;
  variant?: "error" | "not-found" | "forbidden";
  action?: React.ReactNode;
  className?: string;
}

const variants = {
  error: { icon: AlertTriangle, tone: "text-destructive", bg: "bg-destructive/10" },
  "not-found": { icon: FileQuestion, tone: "text-warning", bg: "bg-warning/10" },
  forbidden: { icon: Lock, tone: "text-destructive", bg: "bg-destructive/10" },
} as const;

export function ErrorState({
  title,
  description,
  onRetry,
  variant = "error",
  action,
  className,
}: ErrorStateProps) {
  const config = variants[variant];
  const Icon = config.icon;

  const resolvedTitle =
    title ??
    (variant === "not-found"
      ? "Not found"
      : variant === "forbidden"
        ? "Access denied"
        : "Something went wrong");

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border px-6 py-14 text-center",
        className,
      )}
    >
      <span className={cn("mb-4 flex h-11 w-11 items-center justify-center rounded-lg", config.bg)}>
        <Icon className={cn("h-5 w-5", config.tone)} />
      </span>
      <h3 className="text-sm font-semibold">{resolvedTitle}</h3>
      <p className="mt-1.5 max-w-md text-sm text-muted-foreground">{description}</p>
      <div className="mt-5 flex items-center gap-2">
        {action}
        {onRetry ? (
          <Button variant="outline" onClick={onRetry}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Try again
          </Button>
        ) : null}
      </div>
    </div>
  );
}
