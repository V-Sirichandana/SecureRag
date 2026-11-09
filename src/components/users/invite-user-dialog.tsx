"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { UserPlus } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useInviteUser } from "@/lib/queries";
import { departments, roleDescriptions, roleLabels } from "@/lib/mock/users";
import type { Role } from "@/lib/types";

const schema = z.object({
  email: z.email("Enter a valid work email address"),
  role: z.enum(["owner", "admin", "manager", "member", "viewer"]),
  department: z.string().min(1, "Choose a department"),
  message: z.string().max(300, "Keep the note under 300 characters").optional(),
});

type FormValues = z.infer<typeof schema>;

interface InviteUserDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function InviteUserDialog({ open, onOpenChange }: InviteUserDialogProps) {
  const invite = useInviteUser();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", role: "member", department: "Engineering", message: "" },
  });

  const { handleSubmit, register, formState, reset, setValue, watch } = form;
  const role = watch("role");

  const onSubmit = (values: FormValues) => {
    invite.mutate(values, {
      onSuccess: () => {
        reset();
        onOpenChange(false);
      },
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Invite team member</DialogTitle>
          <DialogDescription>
            They&apos;ll receive an email with a secure link to join Acme Technologies.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="invite-email">Email address</Label>
            <Input
              id="invite-email"
              type="email"
              placeholder="colleague@company.com"
              {...register("email")}
            />
            {formState.errors.email ? (
              <p className="text-xs font-medium text-destructive" role="alert">
                {formState.errors.email.message}
              </p>
            ) : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="invite-role">Role</Label>
              <Select
                value={role}
                onValueChange={(value) =>
                  setValue("role", value as Role, { shouldValidate: true })
                }
              >
                <SelectTrigger id="invite-role" aria-label="Role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(roleLabels) as Role[]).map((value) => (
                    <SelectItem key={value} value={value}>
                      {roleLabels[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">{roleDescriptions[role]}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="invite-department">Department</Label>
              <Select
                value={watch("department")}
                onValueChange={(value) =>
                  setValue("department", value, { shouldValidate: true })
                }
              >
                <SelectTrigger id="invite-department" aria-label="Department">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {departments.map((department) => (
                    <SelectItem key={department} value={department}>
                      {department}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="invite-message">Message (optional)</Label>
            <Textarea
              id="invite-message"
              rows={3}
              placeholder="Welcome aboard — you'll have access to the Engineering collection."
              {...register("message")}
            />
            {formState.errors.message ? (
              <p className="text-xs font-medium text-destructive" role="alert">
                {formState.errors.message.message}
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={invite.isPending}>
              <UserPlus className="mr-2 h-4 w-4" />
              {invite.isPending ? "Sending…" : "Send invitation"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
