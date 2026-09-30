"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  BookOpen,
  ChevronsLeft,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  HelpCircle,
} from "lucide-react";
import { cn, initials } from "@/lib/utils";
import { navSections } from "@/components/layout/nav";
import { OrganizationSwitcher } from "@/components/layout/organization-switcher";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuthStore, useUIStore } from "@/stores/ui";

function isActive(pathname: string, href: string): boolean {
  if (href === "/app/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { state, toggleSidebar, isMobile } = useSidebar();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const collapsed = state === "collapsed" && !isMobile;

  useEffect(() => {
    useUIStore.getState().setMobileSidebarOpen(false);
  }, [pathname]);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  return (
    <Sidebar collapsible="icon" variant="inset" className="border-r">
      <SidebarHeader className="gap-3 px-3 pb-1 pt-3">
        <Link
          href="/app/dashboard"
          className="flex h-9 items-center gap-2.5 rounded-md px-1"
          aria-label="SecureRAG home"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <BookOpen className="h-4 w-4" />
          </span>
          <span
            className={cn(
              "flex-1 overflow-hidden text-[15px] font-semibold tracking-tight transition-all",
              collapsed && "w-0 opacity-0",
            )}
          >
            SecureRAG
          </span>
        </Link>
        <div className={cn(collapsed && "hidden")}>
          <OrganizationSwitcher />
        </div>
        <div className={cn("flex justify-center", !collapsed && "hidden")}>
          <OrganizationSwitcher collapsed />
        </div>
      </SidebarHeader>

      <SidebarContent className="scrollbar-thin px-2 py-3">
        {navSections.map((section) => (
          <SidebarGroup key={section.title}>
            <SidebarGroupLabel className="h-6 px-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
              {section.title}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {section.items.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive(pathname, item.href)}
                      tooltip={item.label}
                      className="h-9"
                    >
                      <Link href={item.href}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter className="gap-2 px-2 pb-3 pt-2">
        <div className={cn("space-y-2", collapsed && "hidden")}>
          <div className="flex items-center gap-2 rounded-lg border bg-muted/40 px-2.5 py-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
              {initials(user?.name ?? "SecureRAG")}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium leading-tight">
                {user?.name ?? "Vishvendra Vadla"}
              </span>
              <span className="block truncate text-xs capitalize text-muted-foreground">
                {user?.role ?? "owner"} · {user?.department ?? "Executive"}
              </span>
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <UserMenuButton collapsed={false} />
            <Button
              variant="ghost"
              size="sm"
              className="h-9 flex-1 justify-start gap-2 text-muted-foreground hover:text-foreground"
              onClick={handleLogout}
            >
              <LogOut className="h-4 w-4" />
              Log out
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9 shrink-0 text-muted-foreground"
              onClick={toggleSidebar}
              aria-label="Collapse sidebar"
            >
              <ChevronsLeft className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className={cn("flex flex-col items-center gap-2", !collapsed && "hidden")}>
          <UserMenuButton collapsed />
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 text-muted-foreground"
            onClick={toggleSidebar}
            aria-label="Expand sidebar"
          >
            <ChevronsLeft className="h-4 w-4 rotate-180" />
          </Button>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

function UserMenuButton({ collapsed }: { collapsed: boolean }) {
  const user = useAuthStore((state) => state.user);
  const router = useRouter();
  const logout = useAuthStore((state) => state.logout);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Open account menu"
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold text-secondary-foreground transition-colors hover:bg-secondary/80",
            collapsed && "h-8 w-8",
          )}
        >
          {initials(user?.name ?? "Vishvendra Vadla")}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={collapsed ? "start" : "end"} className="w-60">
        <DropdownMenuLabel>
          <span className="block truncate font-medium">{user?.name ?? "Vishvendra Vadla"}</span>
          <span className="block truncate text-xs font-normal text-muted-foreground">
            {user?.email ?? "vishvendra@acmetech.io"}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/app/settings/general">
            <LayoutDashboard className="mr-2 h-4 w-4" />
            Organization settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/app/chat">
            <MessageSquare className="mr-2 h-4 w-4" />
            Ask the assistant
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/app/settings/security">
            <HelpCircle className="mr-2 h-4 w-4" />
            Security centre
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive">
          <LogOut className="mr-2 h-4 w-4" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
