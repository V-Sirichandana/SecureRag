"use client";

import * as React from "react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { useAuthStore, useUIStore } from "@/stores/ui";
import { getMe } from "@/lib/api/auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const authLogin = useAuthStore((state) => state.login);
  const [hydrating, setHydrating] = React.useState(!user);

  useEffect(() => {
    if (user) {
      setHydrating(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const session = await getMe();
        if (cancelled) return;
        authLogin(session.user, session.organizations);
        useUIStore.getState().setActiveOrganization(session.user.organizationId);
      } catch {
        if (cancelled) return;
        router.replace("/login");
      } finally {
        if (!cancelled) setHydrating(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user, router, authLogin]);

  if (hydrating || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <span
            className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent"
            aria-hidden="true"
          />
          <p className="text-sm text-muted-foreground">Loading your workspace…</p>
        </div>
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}


