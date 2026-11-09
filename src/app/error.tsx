"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/common/error-state";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-background px-6 py-16">
      <div className="w-full max-w-xl">
        <ErrorState
          title="Something went wrong"
          description={
            error.digest
              ? `The application hit an unexpected error. Reference: ${error.digest}`
              : "The application hit an unexpected error while rendering this view."
          }
          onRetry={reset}
          action={
            <Button variant="outline" asChild>
              <Link href="/app/dashboard">Back to dashboard</Link>
            </Button>
          }
        />
        <p className="mt-4 text-center text-xs text-muted-foreground">
          If this keeps happening, check the browser console and report the reference above to
          your administrator.
        </p>
      </div>
    </main>
  );
}
