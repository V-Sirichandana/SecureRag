"use client";

import { Loader2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SettingsSectionProps {
  id: string;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  onSave?: () => void;
  saveLabel?: string;
  saving?: boolean;
  dirty?: boolean;
  className?: string;
}

export function SettingsSection({
  id,
  title,
  description,
  children,
  footer,
  onSave,
  saveLabel = "Save changes",
  saving,
  dirty = true,
  className,
}: SettingsSectionProps) {
  return (
    <Card id={id} className={cn("gap-0 py-0 scroll-mt-28", className)}>
      <CardHeader className="border-b">
        <CardTitle className="text-base font-semibold">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="space-y-5 p-5">{children}</CardContent>
      {onSave || footer ? (
        <div className="flex flex-wrap items-center justify-end gap-3 border-t bg-muted/20 px-5 py-3.5">
          {footer}
          {onSave ? (
            <Button onClick={onSave} disabled={saving || !dirty}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {saving ? "Saving…" : saveLabel}
            </Button>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

interface FieldRowProps {
  label: string;
  hint?: string;
  control: React.ReactNode;
}

export function FieldRow({ label, hint, control }: FieldRowProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="space-y-1">
        <p className="text-sm font-medium">{label}</p>
        {hint ? <p className="max-w-md text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}
