"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Building2 } from "lucide-react";
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
import { FieldRow, SettingsSection } from "@/components/settings/settings-section";
import { useCollections, useGeneralSettings, useSaveGeneralSettings } from "@/lib/queries";

const schema = z.object({
  organizationName: z.string().min(2, "Organization name is required"),
  description: z.string().max(280, "Keep the description under 280 characters"),
  defaultCollectionId: z.string().min(1, "Pick a default collection"),
  supportEmail: z.email("Enter a valid email address"),
});

type FormValues = z.infer<typeof schema>;

export default function GeneralSettingsPage() {
  const current = useGeneralSettings();
  const collections = useCollections();
  const save = useSaveGeneralSettings();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    values: current.data,
    defaultValues: {
      organizationName: "",
      description: "",
      defaultCollectionId: "",
      supportEmail: "",
    },
  });

  const { handleSubmit, register, formState, setValue, watch, reset } = form;
  const dirty = formState.isDirty;

  const onSubmit = (values: FormValues) => {
    save.mutate(values, {
      onSuccess: (saved) => reset(saved),
    });
  };

  if (current.isError) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-5">
        <p className="text-sm font-medium">We couldn&apos;t load organization settings.</p>
        <Button variant="outline" size="sm" onClick={() => void current.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6" noValidate>
      <SettingsSection
        id="organization"
        title="Organization"
        description="Displayed across the workspace and used in invitations."
        dirty={dirty}
        saving={save.isPending}
        onSave={() => void handleSubmit(onSubmit)()}
      >
        <div className="flex items-center gap-4">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Building2 className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium">
              {watch("organizationName") || "Your organization"}
            </p>
            <p className="text-xs text-muted-foreground">
              Avatar is generated from your initials until a logo is uploaded
            </p>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="org-name">Organization name</Label>
          <Input id="org-name" placeholder="Acme Technologies" {...register("organizationName")} />
          {formState.errors.organizationName ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {formState.errors.organizationName.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="org-description">Description</Label>
          <Textarea
            id="org-description"
            rows={3}
            placeholder="What this workspace is used for…"
            {...register("description")}
          />
          <div className="flex justify-between gap-3">
            {formState.errors.description ? (
              <p className="text-xs font-medium text-destructive" role="alert">
                {formState.errors.description.message}
              </p>
            ) : (
              <span />
            )}
            <span className="text-xs tabular-nums text-muted-foreground">
              {(watch("description") ?? "").length}/280
            </span>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="org-email">Support email</Label>
          <Input
            id="org-email"
            type="email"
            placeholder="platform@example.com"
            {...register("supportEmail")}
          />
          {formState.errors.supportEmail ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {formState.errors.supportEmail.message}
            </p>
          ) : null}
        </div>
      </SettingsSection>

      <SettingsSection
        id="defaults"
        title="Workspace defaults"
        description="Applied to new members and chat sessions."
        footer={
          <span className="mr-auto text-xs text-muted-foreground">
            {dirty ? "You have unsaved changes" : "All changes saved"}
          </span>
        }
        dirty={dirty}
        saving={save.isPending}
        onSave={() => void handleSubmit(onSubmit)()}
      >
        <FieldRow
          label="Default collection"
          hint="New conversations start against this collection."
          control={
            <Select
              value={watch("defaultCollectionId")}
              onValueChange={(value) =>
                setValue("defaultCollectionId", value, { shouldDirty: true, shouldValidate: true })
              }
            >
              <SelectTrigger className="w-full sm:w-72" aria-label="Default collection">
                <SelectValue placeholder={collections.isPending ? "Loading…" : "Select a collection"} />
              </SelectTrigger>
              <SelectContent>
                {collections.data?.map((collection) => (
                  <SelectItem key={collection.id} value={collection.id}>
                    {collection.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
        />
      </SettingsSection>
    </form>
  );
}
