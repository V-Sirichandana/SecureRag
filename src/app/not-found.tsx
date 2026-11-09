import Link from "next/link";
import { ShieldQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-6 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <ShieldQuestion className="h-7 w-7" />
      </span>

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Error 404
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">This page doesn&apos;t exist</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          The link may be outdated, or the resource was deleted from this workspace. Your
          organization&apos;s data is unaffected.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button asChild>
          <Link href="/app/dashboard">Back to dashboard</Link>
        </Button>
        <Button variant="outline" asChild>
          <Link href="/app/documents">Browse documents</Link>
        </Button>
      </div>
    </main>
  );
}
