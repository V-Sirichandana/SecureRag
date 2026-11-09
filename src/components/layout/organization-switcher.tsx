"use client";

import Link from "next/link";
import { useState } from "react";
import { Building2, Check, ChevronsUpDown, Plus, ShieldCheck } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useAuthStore, useUIStore } from "@/stores/ui";

interface OrgSummary {
  id: string;
  name: string;
  plan: string;
  memberCount: number;
}

function initialsBadge(name: string) {
  return name
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export function OrganizationSwitcher({ collapsed = false }: { collapsed?: boolean }) {
  const [open, setOpen] = useState(false);
  const organizations = useAuthStore((state) => state.organizations);
  const activeId = useUIStore((state) => state.activeOrganizationId);
  const setActiveOrganization = useUIStore((state) => state.setActiveOrganization);

  const active = organizations.find((org) => org.id === activeId) ?? organizations[0];
  if (!active) return null;

  const select = (id: string) => {
    setActiveOrganization(id);
    setOpen(false);
  };

  if (collapsed) {
    return (
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={`Current organization: ${active.name}. Open organization switcher`}
            className="mx-auto flex h-9 w-9 items-center justify-center rounded-md bg-primary text-[11px] font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {initialsBadge(active.name)}
          </button>
        </DropdownMenuTrigger>
        <OrganizationMenu organizations={organizations} activeId={active.id} onSelect={select} />
      </DropdownMenu>
    );
  }

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          className="w-full justify-between gap-2 px-2.5"
          aria-label={`Current organization: ${active.name}. Open organization switcher`}
        >
          <span className="flex min-w-0 items-center gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-primary text-[10px] font-semibold text-primary-foreground">
              {initialsBadge(active.name)}
            </span>
            <span className="truncate text-sm font-medium">{active.name}</span>
          </span>
          <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <OrganizationMenu organizations={organizations} activeId={active.id} onSelect={select} />
    </DropdownMenu>
  );
}

function OrganizationMenu({
  organizations,
  activeId,
  onSelect,
}: {
  organizations: OrgSummary[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <DropdownMenuContent align="start" className="w-72">
      <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">
        Organizations
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      {organizations.map((org) => (
        <DropdownMenuItem key={org.id} onSelect={() => onSelect(org.id)} className="gap-2.5">
          <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium">{org.name}</span>
            <span className="block text-xs text-muted-foreground">
              {org.plan} · {org.memberCount} members
            </span>
          </span>
          {org.id === activeId ? <Check className="h-4 w-4 shrink-0 text-primary" /> : null}
        </DropdownMenuItem>
      ))}
      <DropdownMenuSeparator />
      <DropdownMenuItem asChild>
        <Link href="/app/settings/general">
          <Plus className="mr-2 h-4 w-4" />
          Create organization
        </Link>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <div className="flex items-center gap-2 px-2 py-1.5 text-xs text-muted-foreground">
        <ShieldCheck className="h-3.5 w-3.5 text-success" />
        Each organization is an isolated tenant
      </div>
    </DropdownMenuContent>
  );
}
