"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
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
import { useCreateCollection } from "@/lib/queries";

const schema = z.object({
  name: z.string().min(2, "Give the collection a name"),
  description: z.string().max(240, "Keep the description under 240 characters"),
  visibility: z.enum(["everyone", "members", "restricted"]),
});

type FormValues = z.infer<typeof schema>;

interface CreateCollectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateCollectionDialog({ open, onOpenChange }: CreateCollectionDialogProps) {
  const mutation = useCreateCollection();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", description: "", visibility: "members" },
  });

  const { handleSubmit, register, formState, reset, setValue, watch } = form;
  const visibility = watch("visibility");

  const onSubmit = (values: FormValues) => {
    mutation.mutate(values, {
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
          <DialogTitle>New collection</DialogTitle>
          <DialogDescription>
            Collections group related documents and inherit a single set of permissions.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="collection-name">Name</Label>
            <Input id="collection-name" placeholder="HR Knowledge" {...register("name")} />
            {formState.errors.name ? (
              <p className="text-xs font-medium text-destructive" role="alert">
                {formState.errors.name.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="collection-description">Description</Label>
            <Textarea
              id="collection-description"
              rows={3}
              placeholder="Policies, handbooks and onboarding documentation…"
              {...register("description")}
            />
            <p className="text-xs text-muted-foreground">
              {formState.errors.description?.message ?? "Optional, but helpful for search."}
            </p>
          </div>

          <div className="space-y-2">
            <Label>Visibility</Label>
            <Select
              value={visibility}
              onValueChange={(value) =>
                setValue("visibility", value as FormValues["visibility"], { shouldValidate: true })
              }
            >
              <SelectTrigger aria-label="Collection visibility">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="everyone">Everyone in the organization</SelectItem>
                <SelectItem value="members">Only assigned members</SelectItem>
                <SelectItem value="restricted">Restricted — owner approval required</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Creating…" : "Create collection"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
