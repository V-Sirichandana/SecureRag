import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/common/error-state";

export default function ForbiddenPage() {
  return (
    <div className="mx-auto w-full max-w-3xl p-4 sm:p-6 lg:p-8">
      <ErrorState
        variant="forbidden"
        title="You don't have access to this resource"
        description="Your role does not include the permission required for this page. Ask an organization owner or admin to grant it."
        action={
          <>
            <Button asChild>
              <Link href="/app/dashboard">Back to dashboard</Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/app/roles">Review permissions</Link>
            </Button>
          </>
        }
      />
      <p className="mt-4 text-center text-xs text-muted-foreground">
        Access decisions are always made by the backend against your authenticated principal —
        this screen is informational only.
      </p>
    </div>
  );
}
