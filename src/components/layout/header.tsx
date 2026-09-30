"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, HelpCircle, Lock, Menu, Search } from "lucide-react";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Notifications } from "@/components/layout/notifications";
import { buildBreadcrumbs, pageTitle } from "@/components/layout/nav";
import { useUIStore } from "@/stores/ui";
import { cn } from "@/lib/utils";

function isMac() {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad/.test(navigator.platform);
}

export function AppHeader() {
  const pathname = usePathname();
  const { isMobile, toggleSidebar } = useSidebar();
  const setCommandOpen = useUIStore((state) => state.setCommandPaletteOpen);
  const crumbs = buildBreadcrumbs(pathname);
  const title = pageTitle(pathname);
  const platform = typeof navigator !== "undefined" && isMac() ? "⌘" : "Ctrl";

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur-md supports-[backdrop-filter]:bg-background/70 md:px-6">
      <button
        type="button"
        onClick={toggleSidebar}
        aria-label="Toggle navigation sidebar"
        className={cn(
          "inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground lg:hidden",
        )}
      >
        <Menu className="h-4.5 w-4.5" />
      </button>

      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        {isMobile ? null : <SidebarTrigger className="-ml-1 h-8 w-8 text-muted-foreground" />}
        <div className="hidden min-w-0 items-center gap-2 md:flex">
          <Breadcrumb>
            <BreadcrumbList className="flex-nowrap gap-1">
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link href="/app/dashboard" className="text-muted-foreground">
                    Acme Technologies
                  </Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              {crumbs.map((crumb, index) => (
                <div key={crumb.href} className="flex items-center gap-1">
                  <BreadcrumbSeparator>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </BreadcrumbSeparator>
                  <BreadcrumbItem>
                    {index === crumbs.length - 1 ? (
                      <BreadcrumbPage className="font-medium">{crumb.label}</BreadcrumbPage>
                    ) : (
                      <BreadcrumbLink asChild>
                        <Link href={crumb.href}>{crumb.label}</Link>
                      </BreadcrumbLink>
                    )}
                  </BreadcrumbItem>
                </div>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
        </div>
        <h1 className={cn("truncate text-sm font-semibold tracking-tight md:hidden")}>{title}</h1>

        <span className="ml-2 hidden items-center gap-1.5 rounded-full border bg-muted/50 px-2.5 py-1 text-[11px] font-medium text-muted-foreground xl:inline-flex">
          <Lock className="h-3 w-3 text-success" />
          Organization isolated
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setCommandOpen(true)}
          className="hidden h-8 items-center gap-2 rounded-md border bg-muted/40 px-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground sm:inline-flex"
          aria-label="Open global search"
        >
          <Search className="h-3.5 w-3.5" />
          <span>Search…</span>
          <kbd className="pointer-events-none ml-2 inline-flex h-5 select-none items-center gap-0.5 rounded border bg-background px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
            {platform} K
          </kbd>
        </button>

        <Button
          variant="ghost"
          size="icon"
          className="sm:hidden"
          onClick={() => setCommandOpen(true)}
          aria-label="Search"
        >
          <Search className="h-[1.15rem] w-[1.15rem]" />
        </Button>

        <Notifications />

        <ThemeToggle />

        <Button variant="ghost" size="icon" aria-label="Help and documentation" asChild>
          <Link href="/app/settings/general">
            <HelpCircle className="h-[1.15rem] w-[1.15rem]" />
          </Link>
        </Button>

        <Separator orientation="vertical" className="mx-1 hidden h-6 sm:block" />
      </div>
    </header>
  );
}
