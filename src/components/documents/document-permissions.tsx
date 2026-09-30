"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Checkbox } from "@/components/ui/checkbox";
import { useUpdateDocumentPermissions } from "@/lib/queries";
import { roleLabels } from "@/lib/mock/users";
import type { Role } from "@/lib/types";

type Scope = "everyone" | "members" | "roles" | "users";

const scopes: { value: Scope; label: string; description: string }[] = [
  {
    value: "everyone",
    label: "Everyone",
    description: "Any authenticated user in this organization can read this document.",
  },
  {
    value: "members",
    label: "Organization members",
    description: "Only active members of the current organization.",
  },
  {
    value: "roles",
    label: "Specific roles",
    description: "Restrict access to one or more roles.",
  },
  {
    value: "users",
    label: "Specific users",
    description: "Grant access to named individuals only.",
  },
];

const roleOptions: Role[] = ["owner", "admin", "manager", "member", "viewer"];

const userOptions = [
  { id: "usr_sarah", name: "Sarah Johnson" },
  { id: "usr_alex", name: "Alex Morgan" },
  { id: "usr_daniel", name: "Daniel Smith" },
  { id: "usr_priya", name: "Priya Nair" },
];

export function DocumentPermissions({ documentId }: { documentId: string }) {
  const [scope, setScope] = React.useState<Scope>("members");
  const [roles, setRoles] = React.useState<Role[]>(["admin", "manager"]);
  const [users, setUsers] = React.useState<string[]>([]);
  const mutation = useUpdateDocumentPermissions();

  const toggle = <T,>(list: T[], value: T): T[] =>
    list.includes(value) ? list.filter((item) => item !== value) : [...list, value];

  const save = () => {
    mutation.mutate({
      id: documentId,
      scope,
      targets: scope === "roles" ? roles : scope === "users" ? users : [],
    });
  };

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold">Who can access this document?</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Permissions are enforced by the backend; this UI only reflects the current policy.
          </p>
        </div>

        <RadioGroup
          value={scope}
          onValueChange={(value) => setScope(value as Scope)}
          className="gap-2"
          aria-label="Document access scope"
        >
          {scopes.map((option) => (
            <label
              key={option.value}
              className="flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition-colors hover:bg-muted/50 has-[button[data-state=checked]]:border-primary/50 has-[button[data-state=checked]]:bg-primary/5"
            >
              <RadioGroupItem
                value={option.value}
                id={`scope-${option.value}`}
                className="mt-0.5"
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{option.label}</span>
                <span className="block text-xs text-muted-foreground">{option.description}</span>
              </span>
            </label>
          ))}
        </RadioGroup>
      </div>

      {scope === "roles" ? (
        <div className="space-y-2.5 rounded-lg border p-4">
          <Label className="text-sm font-semibold">Roles with access</Label>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {roleOptions.map((role) => (
              <label key={role} className="flex items-center gap-2.5 text-sm">
                <Checkbox
                  checked={roles.includes(role)}
                  onCheckedChange={() => setRoles((current) => toggle(current, role))}
                />
                <span className="capitalize">{roleLabels[role]}</span>
              </label>
            ))}
          </div>
        </div>
      ) : null}

      {scope === "users" ? (
        <div className="space-y-2.5 rounded-lg border p-4">
          <Label className="text-sm font-semibold">Users with access</Label>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {userOptions.map((user) => (
              <label key={user.id} className="flex items-center gap-2.5 text-sm">
                <Checkbox
                  checked={users.includes(user.id)}
                  onCheckedChange={() => setUsers((current) => toggle(current, user.id))}
                />
                <span>{user.name}</span>
              </label>
            ))}
          </div>
        </div>
      ) : null}

      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save permissions"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Changes are written to the audit log immediately.
        </p>
      </div>
    </div>
  );
}
