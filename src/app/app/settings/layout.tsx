"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, Bot, CreditCard, ShieldCheck, SlidersHorizontal } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { cn } from "@/lib/utils";

interface SettingsNavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  hint: string;
}

const settingsNav: SettingsNavItem[] = [
  {
    label: "General",
    href: "/app/settings/general",
    icon: SlidersHorizontal,
    hint: "Organization profile and defaults",
  },
  {
    label: "Security",
    href: "/app/settings/security",
    icon: ShieldCheck,
    hint: "MFA, sessions, SSO and access",
  },
  {
    label: "AI Configuration",
    href: "/app/settings/ai",
    icon: Bot,
    hint: "Models, retrieval and citations",
  },
  {
    label: "Notifications",
    href: "/app/settings/notifications",
    icon: Bell,
    hint: "Email digests and alerts",
  },
  {
    label: "Billing",
    href: "/app/settings/billing",
    icon: CreditCard,
    hint: "Plan, seats and invoices",
  },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Settings"
        description="Organization-wide configuration. Changes apply to every member of this tenant."
      />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <nav
          aria-label="Settings sections"
          className="scrollbar-thin -mx-1 flex gap-1 overflow-x-auto px-1 pb-1 lg:sticky lg:top-6 lg:mx-0 lg:w-60 lg:shrink-0 lg:flex-col lg:overflow-visible lg:px-0 lg:pb-0"
        >
          {settingsNav.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-w-max items-start gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors lg:min-w-0",
                  active
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <item.icon className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="min-w-0">
                  <span className="block whitespace-nowrap">{item.label}</span>
                  <span className="mt-0.5 hidden text-xs font-normal text-muted-foreground lg:block">
                    {item.hint}
                  </span>
                </span>
              </Link>
            );
          })}
        </nav>

        <div className="min-w-0 flex-1 space-y-6">{children}</div>
      </div>
    </div>
  );
}
