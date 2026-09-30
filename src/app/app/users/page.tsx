"use client";

import * as React from "react";
import { toast } from "sonner";
import { Search, ShieldCheck, UserPlus, Users } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { InviteUserDialog } from "@/components/users/invite-user-dialog";
import { UserTable } from "@/components/users/user-table";
import {
  useRemoveUser,
  useUpdateUserRole,
  useUpdateUserStatus,
  useUsers,
} from "@/lib/queries";
import { roleLabels } from "@/lib/mock/users";
import { useDebounce } from "@/hooks/use-client";
import type { Role, User } from "@/lib/types";

export default function UsersPage() {
  const [search, setSearch] = React.useState("");
  const [role, setRole] = React.useState<"all" | Role>("all");
  const [inviteOpen, setInviteOpen] = React.useState(false);
  const [pendingRemove, setPendingRemove] = React.useState<User | null>(null);

  const debounced = useDebounce(search, 250);
  const users = useUsers();
  const changeRole = useUpdateUserRole();
  const toggleStatus = useUpdateUserStatus();
  const removeUser = useRemoveUser();

  const filtered = (users.data ?? []).filter((user) => {
    const matchesSearch =
      !debounced ||
      user.name.toLowerCase().includes(debounced.toLowerCase()) ||
      user.email.toLowerCase().includes(debounced.toLowerCase()) ||
      user.department.toLowerCase().includes(debounced.toLowerCase());
    const matchesRole = role === "all" || user.role === role;
    return matchesSearch && matchesRole;
  });

  const activeCount = (users.data ?? []).filter((user) => user.status === "active").length;

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Users"
        description="Manage who can access your organization's knowledge base and what they can do."
        actions={
          <Button onClick={() => setInviteOpen(true)}>
            <UserPlus className="mr-2 h-4 w-4" />
            Invite user
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-success" />
          {activeCount} active · role-based access
        </Badge>
        <Badge variant="outline" className="text-muted-foreground">
          {(users.data ?? []).length} total seats
        </Badge>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name, email or department…"
            className="pl-9"
            aria-label="Search users"
          />
        </div>
        <Select value={role} onValueChange={(value) => setRole(value as "all" | Role)}>
          <SelectTrigger className="w-full sm:w-44" aria-label="Filter by role">
            <SelectValue placeholder="Role" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All roles</SelectItem>
            {(Object.keys(roleLabels) as Role[]).map((value) => (
              <SelectItem key={value} value={value}>
                {roleLabels[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card className="overflow-hidden py-0">
        {users.isError ? (
          <div className="p-6">
            <ErrorState
              title="We couldn't load your team"
              description="The directory service didn't respond."
              onRetry={() => void users.refetch()}
            />
          </div>
        ) : (
          <UserTable
            users={filtered}
            isPending={users.isPending}
            emptyState={
              <div className="p-6">
                <EmptyState
                  icon={Users}
                  title={debounced || role !== "all" ? "No matching team members" : "No team members yet"}
                  description={
                    debounced || role !== "all"
                      ? "Try a different search term or clear the role filter."
                      : "Invite your colleagues to collaborate on your organization's knowledge base."
                  }
                  action={
                    debounced || role !== "all" ? (
                      <Button
                        variant="outline"
                        onClick={() => {
                          setSearch("");
                          setRole("all");
                        }}
                      >
                        Clear filters
                      </Button>
                    ) : (
                      <Button onClick={() => setInviteOpen(true)}>
                        <UserPlus className="mr-2 h-4 w-4" />
                        Invite user
                      </Button>
                    )
                  }
                />
              </div>
            }
            onChangeRole={(user, nextRole) =>
              changeRole.mutate(
                { id: user.id, role: nextRole },
                {
                  onSuccess: () =>
                    toast.success(`${user.name} is now ${roleLabels[nextRole].toLowerCase()}.`),
                },
              )
            }
            onToggleStatus={(user) =>
              toggleStatus.mutate(
                { id: user.id, status: user.status === "disabled" ? "active" : "disabled" },
                {
                  onSuccess: () =>
                    toast.success(
                      user.status === "disabled"
                        ? `${user.name} re-enabled.`
                        : `${user.name} disabled.`,
                    ),
                },
              )
            }
            onRemove={setPendingRemove}
          />
        )}
      </Card>

      <InviteUserDialog open={inviteOpen} onOpenChange={setInviteOpen} />

      <AlertDialog
        open={Boolean(pendingRemove)}
        onOpenChange={(open) => {
          if (!open) setPendingRemove(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {pendingRemove?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              They will immediately lose access to all collections and any active sessions will be
              revoked. Their past activity remains in the audit log.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={(event) => {
                event.preventDefault();
                if (!pendingRemove) return;
                removeUser.mutate(pendingRemove.id, {
                  onSuccess: () => {
                    toast.success(`${pendingRemove.name} removed.`);
                    setPendingRemove(null);
                  },
                });
              }}
            >
              Remove user
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
