"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { FieldRow, SettingsSection } from "@/components/settings/settings-section";
import { useNotificationSettings, useSaveNotificationSettings } from "@/lib/queries";
import type { SettingsNotifications } from "@/lib/types";

export default function NotificationsSettingsPage() {
  const current = useNotificationSettings();
  const save = useSaveNotificationSettings();
  const [draft, setDraft] = React.useState<SettingsNotifications | null>(null);

  React.useEffect(() => {
    if (current.data) setDraft(current.data);
  }, [current.data]);

  const dirty = Boolean(
    draft && current.data && JSON.stringify(draft) !== JSON.stringify(current.data),
  );

  const update = <K extends keyof SettingsNotifications>(
    key: K,
    value: SettingsNotifications[K],
  ) => setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  if (current.isError) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-5">
        <p className="text-sm font-medium">We couldn&apos;t load notification settings.</p>
        <Button variant="outline" size="sm" onClick={() => void current.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="h-48 animate-pulse rounded-xl border bg-muted/40" />
        ))}
      </div>
    );
  }

  const saveChanges = () => save.mutate(draft);

  return (
    <div className="space-y-6">
      <SettingsSection
        id="security-alerts"
        title="Security & access"
        description="Immediate alerts for events that affect your organization's security."
        dirty={dirty}
        saving={save.isPending}
        onSave={saveChanges}
      >
        <FieldRow
          label="Security alerts"
          hint="New device sign-ins, MFA changes and failed sign-in bursts."
          control={
            <Switch
              checked={draft.securityAlerts}
              onCheckedChange={(checked) => update("securityAlerts", checked)}
              aria-label="Security alerts"
            />
          }
        />
        <FieldRow
          label="Member activity"
          hint="When someone joins, is invited or changes role."
          control={
            <Switch
              checked={draft.memberJoinedAlerts}
              onCheckedChange={(checked) => update("memberJoinedAlerts", checked)}
              aria-label="Member activity alerts"
            />
          }
        />
      </SettingsSection>

      <SettingsSection
        id="operations-alerts"
        title="Documents & usage"
        description="Operational events across ingestion and consumption."
        dirty={dirty}
        saving={save.isPending}
        onSave={saveChanges}
      >
        <FieldRow
          label="Document processing failures"
          hint="Get notified when ingestion or indexing fails for a document."
          control={
            <Switch
              checked={draft.documentProcessingAlerts}
              onCheckedChange={(checked) => update("documentProcessingAlerts", checked)}
              aria-label="Document processing failure alerts"
            />
          }
        />
        <FieldRow
          label="Usage thresholds"
          hint="Alerts when token or storage usage reaches 80% of the plan quota."
          control={
            <Switch
              checked={draft.usageThresholdAlerts}
              onCheckedChange={(checked) => update("usageThresholdAlerts", checked)}
              aria-label="Usage threshold alerts"
            />
          }
        />
      </SettingsSection>

      <SettingsSection
        id="email-digests"
        title="Email digests"
        description="Recurring summaries delivered to organization admins."
        dirty={dirty}
        saving={save.isPending}
        onSave={saveChanges}
        footer={
          <span className="mr-auto text-xs text-muted-foreground">
            {dirty ? "You have unsaved changes" : "All changes saved"}
          </span>
        }
      >
        <FieldRow
          label="Weekly activity digest"
          hint="Queries, top collections and retrieval quality every Monday."
          control={
            <Switch
              checked={draft.weeklyDigest}
              onCheckedChange={(checked) => update("weeklyDigest", checked)}
              aria-label="Weekly activity digest"
            />
          }
        />
        <FieldRow
          label="Product updates"
          hint="Release notes and improvement announcements."
          control={
            <Switch
              checked={draft.productUpdates}
              onCheckedChange={(checked) => update("productUpdates", checked)}
              aria-label="Product update emails"
            />
          }
        />
      </SettingsSection>
    </div>
  );
}
