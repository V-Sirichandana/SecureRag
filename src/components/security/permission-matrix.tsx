"use client";

import * as React from "react";
import { toast } from "sonner";
import { Check, Lock, Minus } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { permissionLabels, permissionMatrix as seed } from "@/lib/mock/settings";
import { roleLabels } from "@/lib/mock/users";
import { cn } from "@/lib/utils";
import type { PermissionKey, PermissionMatrix, Role } from "@/lib/types";

const roles: Role[] = ["owner", "admin", "manager", "member", "viewer"];

export function PermissionMatrix() {
  const [matrix, setMatrix] = React.useState<PermissionMatrix>(seed);
  const [dirty, setDirty] = React.useState(false);

  const toggle = (permission: PermissionKey, role: Role) => {
    if (role === "owner") return;
    setMatrix((current) => ({
      ...current,
      [permission]: {
        ...current[permission],
        [role]: !current[permission][role],
      },
    }));
    setDirty(true);
  };

  const save = () => {
    setDirty(false);
    toast.success("Role permissions updated.");
  };

  const enabledCount = (role: Role) =>
    (Object.keys(matrix) as PermissionKey[]).filter((key) => matrix[key][role]).length;

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-4 space-y-0">
        <div className="space-y-1.5">
          <CardTitle className="text-base font-semibold">Permission matrix</CardTitle>
          <CardDescription>
            Changes apply to every member holding that role across the organization.
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {dirty ? (
            <Badge variant="outline" className="border-warning/40 text-warning">
              Unsaved changes
            </Badge>
          ) : null}
          <Button onClick={save} disabled={!dirty}>
            Save changes
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {roles.map((role) => (
            <div
              key={role}
              className="rounded-lg border bg-muted/30 px-3.5 py-3 text-center"
            >
              <p className="text-sm font-semibold capitalize">{roleLabels[role]}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {enabledCount(role)} of {Object.keys(matrix).length} permissions
              </p>
            </div>
          ))}
        </div>

        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="min-w-[220px]">Permission</TableHead>
                {roles.map((role) => (
                  <TableHead key={role} className="w-24 text-center capitalize">
                    {roleLabels[role]}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {(Object.keys(permissionLabels) as PermissionKey[]).map((permission) => (
                <TableRow key={permission}>
                  <TableCell className="font-medium">
                    {permissionLabels[permission]}
                  </TableCell>
                  {roles.map((role) => {
                    const checked = matrix[permission][role];
                    const locked = role === "owner";
                    return (
                      <TableCell key={role} className="text-center">
                        <span className="inline-flex items-center justify-center gap-1.5">
                          <Switch
                            checked={checked}
                            disabled={locked}
                            onCheckedChange={() => toggle(permission, role)}
                            aria-label={`${permissionLabels[permission]} for ${roleLabels[role]}`}
                            className={cn(locked && "opacity-70")}
                          />
                          {locked ? (
                            <Lock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                          ) : null}
                        </span>
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Check className="h-3.5 w-3.5 text-success" /> Granted
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Minus className="h-3.5 w-3.5" /> Not granted
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Lock className="h-3.5 w-3.5" /> Owner permissions are immutable
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
