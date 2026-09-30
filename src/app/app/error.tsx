"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/common/error-state";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto w-full max-w-3xl p-4 sm:p-6 lg:p-8">
      <ErrorState
        title="We couldn't load this view"
        description={
          error.digest
            ? `An unexpected error occurred while rendering this page. Reference: ${error.digest}`
            : "An unexpected error occurred while rendering this page."
        }
        onRetry={reset}
        action={
          <Button variant="outline" asChild>
            <Link href="/app/dashboard">Back to dashboard</Link>
          </Button>
        }
      />
    </div>
  );
}
