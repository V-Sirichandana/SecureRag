"use client";

import { Bell, FileText, KeyRound, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { timeAgo } from "@/lib/utils";

const notifications = [
  {
    id: "n1",
    icon: FileText,
    title: "Employee Handbook.pdf finished indexing",
    detail: "312 chunks · HR collection",
    timestamp: new Date(Date.now() - 2 * 60_000).toISOString(),
  },
  {
    id: "n2",
    icon: UserPlus,
    title: "Elena Petrova accepted your invitation",
    detail: "Member · Design",
    timestamp: new Date(Date.now() - 45 * 60_000).toISOString(),
  },
  {
    id: "n3",
    icon: KeyRound,
    title: "API key “Development” is unused",
    detail: "Consider revoking unused credentials",
    timestamp: new Date(Date.now() - 6 * 3_600_000).toISOString(),
  },
];

export function Notifications() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
          <Bell className="h-[1.15rem] w-[1.15rem]" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-primary" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Notifications</span>
          <span className="text-xs font-normal text-muted-foreground">3 new</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          {notifications.map((item) => (
            <DropdownMenuItem key={item.id} className="items-start gap-3 py-2.5">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-secondary">
                <item.icon className="h-4 w-4 text-secondary-foreground" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium leading-snug">{item.title}</span>
                <span className="block text-xs text-muted-foreground">{item.detail}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground/70">
                  {timeAgo(item.timestamp)}
                </span>
              </span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="justify-center text-xs text-muted-foreground">
          Mark all as read
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
