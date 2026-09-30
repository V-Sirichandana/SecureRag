import { Skeleton } from "@/components/common/skeletons";

export function RouteLoading({
  cards = 4,
  chart = true,
  rows = 6,
}: {
  cards?: number;
  chart?: boolean;
  rows?: number;
}) {
  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="space-y-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: cards }).map((_, index) => (
          <div key={index} className="h-32 animate-pulse rounded-xl border bg-muted/40" />
        ))}
      </div>

      {chart ? (
        <div className="h-80 animate-pulse rounded-xl border bg-muted/40" />
      ) : null}

      <div className="space-y-3 rounded-xl border p-4">
        {Array.from({ length: rows }).map((_, index) => (
          <div key={index} className="flex items-center gap-4">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 flex-1" />
            <Skeleton className="h-4 w-20" />
          </div>
        ))}
      </div>
    </div>
  );
}
