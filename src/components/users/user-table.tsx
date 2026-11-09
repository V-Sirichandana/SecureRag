"use client";

import { Ban, MoreHorizontal, RefreshCcw, ShieldCheck, Trash2, UserCog } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { UserStatusBadge } from "@/components/common/status-badge";
import { roleLabels } from "@/lib/mock/users";
import { initials, timeAgo } from "@/lib/utils";
import type { Role, User } from "@/lib/types";

const roleTone: Record<Role, string> = {
  owner: "bg-primary/10 text-primary",
  admin: "bg-chart-5/15 text-chart-5",
  manager: "bg-chart-2/15 text-chart-2",
  member: "bg-muted text-muted-foreground",
  viewer: "bg-muted text-muted-foreground",
};

interface UserTableProps {
  users: User[];
  isPending?: boolean;
  onChangeRole: (user: User, role: Role) => void;
  onToggleStatus: (user: User) => void;
  onRemove: (user: User) => void;
  emptyState?: React.ReactNode;
}

export function UserTable({
  users,
  isPending,
  onChangeRole,
  onToggleStatus,
  onRemove,
  emptyState,
}: UserTableProps) {
  if (isPending) {
    return (
      <div className="space-y-3 p-4">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="flex animate-pulse items-center gap-4">
            <span className="h-9 w-9 rounded-full bg-muted" />
            <span className="h-4 flex-1 rounded bg-muted" />
            <span className="h-4 w-24 rounded bg-muted" />
            <span className="h-4 w-20 rounded bg-muted" />
          </div>
        ))}
      </div>
    );
  }

  if (users.length === 0) return <>{emptyState}</>;

  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="min-w-[220px]">User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Department</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last active</TableHead>
              <TableHead className="w-12 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    <Avatar className="h-9 w-9">
                      <AvatarFallback className="bg-secondary text-xs font-semibold">
                        {initials(user.name)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{user.name}</p>
                      <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <span
                    className={`inline-flex rounded-md px-2 py-1 text-xs font-medium capitalize ${roleTone[user.role]}`}
                  >
                    {roleLabels[user.role]}
                  </span>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{user.department}</TableCell>
                <TableCell>
                  <UserStatusBadge status={user.status} />
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                  {timeAgo(user.lastActive)}
                </TableCell>
                <TableCell className="text-right">
                  <UserActions
                    user={user}
                    onChangeRole={onChangeRole}
                    onToggleStatus={onToggleStatus}
                    onRemove={onRemove}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="divide-y md:hidden">
        {users.map((user) => (
          <div key={user.id} className="flex items-start gap-3 p-4">
            <Avatar className="h-9 w-9">
              <AvatarFallback className="bg-secondary text-xs font-semibold">
                {initials(user.name)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{user.name}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span
                  className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium capitalize ${roleTone[user.role]}`}
                >
                  {roleLabels[user.role]}
                </span>
                <UserStatusBadge status={user.status} />
                <span className="text-xs text-muted-foreground">{user.department}</span>
              </div>
            </div>
            <UserActions
              user={user}
              onChangeRole={onChangeRole}
              onToggleStatus={onToggleStatus}
              onRemove={onRemove}
            />
          </div>
        ))}
      </div>
    </>
  );
}

function UserActions({
  user,
  onChangeRole,
  onToggleStatus,
  onRemove,
}: {
  user: User;
  onChangeRole: (user: User, role: Role) => void;
  onToggleStatus: (user: User) => void;
  onRemove: (user: User) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground"
          aria-label={`Actions for ${user.name}`}
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuLabel className="text-xs text-muted-foreground">
          {user.email}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <UserCog className="mr-2 h-4 w-4" />
            Change role
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            {(Object.keys(roleLabels) as Role[]).map((role) => (
              <DropdownMenuItem
                key={role}
                onSelect={() => onChangeRole(user, role)}
                className="capitalize"
              >
                <ShieldCheck
                  className={`mr-2 h-4 w-4 ${role === user.role ? "text-primary" : "text-transparent"}`}
                />
                {roleLabels[role]}
              </DropdownMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        <DropdownMenuItem
          onSelect={() => onToggleStatus(user)}
          disabled={user.role === "owner"}
        >
          {user.status === "disabled" ? (
            <>
              <RefreshCcw className="mr-2 h-4 w-4" />
              Re-enable user
            </>
          ) : (
            <>
              <Ban className="mr-2 h-4 w-4" />
              Disable user
            </>
          )}
        </DropdownMenuItem>

        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-destructive focus:text-destructive"
          onSelect={() => onRemove(user)}
          disabled={user.role === "owner"}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          Remove from workspace
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
