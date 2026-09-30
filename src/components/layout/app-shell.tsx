"use client";

import { useEffect } from "react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AppHeader } from "@/components/layout/header";
import { CommandPalette } from "@/components/layout/command-palette";
import { useUIStore } from "@/stores/ui";

export function AppShell({ children }: { children: React.ReactNode }) {
  const collapsed = useUIStore((state) => state.sidebarCollapsed);
  const setCollapsed = useUIStore((state) => state.setSidebarCollapsed);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "[" && (event.metaKey || event.ctrlKey) && event.shiftKey) {
        event.preventDefault();
        setCollapsed(!useUIStore.getState().sidebarCollapsed);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setCollapsed]);

  return (
    <SidebarProvider open={!collapsed} onOpenChange={(open) => setCollapsed(!open)}>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <AppHeader />
        <main className="min-w-0 flex-1">{children}</main>
      </SidebarInset>
      <CommandPalette />
    </SidebarProvider>
  );
}
