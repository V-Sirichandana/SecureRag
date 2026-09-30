"use client";

import { Crown, Shield, Briefcase, User, Eye } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PermissionMatrix } from "@/components/security/permission-matrix";
import { roleDescriptions, roleLabels } from "@/lib/mock/users";
import { useUsers } from "@/lib/queries";
import type { Role } from "@/lib/types";

const roleIcons: Record<Role, LucideIcon> = {
  owner: Crown,
  admin: Shield,
  manager: Briefcase,
  member: User,
  viewer: Eye,
};

const roleTone: Record<Role, string> = {
  owner: "bg-primary/10 text-primary",
  admin: "bg-chart-5/15 text-chart-5",
  manager: "bg-chart-2/15 text-chart-2",
  member: "bg-muted text-muted-foreground",
  viewer: "bg-muted text-muted-foreground",
};

export default function RolesPage() {
  const users = useUsers();
  const roles = Object.keys(roleLabels) as Role[];

  const countFor = (role: Role) =>
    (users.data ?? []).filter((user) => user.role === role).length;

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Roles & Permissions"
        description="Define what each role can do across the workspace. Enforcement happens on the server."
        actions={
          <Badge variant="outline" className="text-muted-foreground">
            {roles.length} roles configured
          </Badge>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {roles.map((role) => {
          const Icon = roleIcons[role];
          return (
            <Card key={role} className="gap-0 py-0">
              <CardContent className="p-5">
                <div className="flex items-center justify-between">
                  <span
                    className={`flex h-9 w-9 items-center justify-center rounded-lg ${roleTone[role]}`}
                  >
                    <Icon className="h-4.5 w-4.5" />
                  </span>
                  <Badge variant="secondary">{countFor(role)} users</Badge>
                </div>
                <p className="mt-3 text-sm font-semibold capitalize">{roleLabels[role]}</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {roleDescriptions[role]}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <PermissionMatrix />

      <p className="text-xs text-muted-foreground">
        The frontend mirrors permissions for usability only. Every request is authorized by the
        backend against the authenticated principal — never trust roles sent from the client.
      </p>
    </div>
  );
}
