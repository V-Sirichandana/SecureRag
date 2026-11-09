"use client";

import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FieldRow, SettingsSection } from "@/components/settings/settings-section";
import { SecurityOverview } from "@/components/settings/security-overview";
import { useSaveSecuritySettings, useSecuritySettings } from "@/lib/queries";
import type { SettingsSecurity } from "@/lib/types";

const CIDR_PATTERN = /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/;

export default function SecuritySettingsPage() {
  const current = useSecuritySettings();
  const save = useSaveSecuritySettings();
  const [draft, setDraft] = React.useState<SettingsSecurity | null>(null);

  React.useEffect(() => {
    if (current.data) setDraft(current.data);
  }, [current.data]);

  const dirty = Boolean(
    draft && current.data && JSON.stringify(draft) !== JSON.stringify(current.data),
  );

  const update = <K extends keyof SettingsSecurity>(key: K, value: SettingsSecurity[K]) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  const saveChanges = () => {
    if (!draft) return;
    if (draft.minPasswordLength < 8) {
      toast.error("Password length must be at least 8 characters.");
      return;
    }
    if (draft.sessionTimeoutMinutes < 5 || draft.sessionTimeoutMinutes > 480) {
      toast.error("Session timeout must be between 5 and 480 minutes.");
      return;
    }
    if (draft.ipAllowlistEnabled) {
      const invalid = draft.ipAllowlist.find((entry) => !CIDR_PATTERN.test(entry.trim()));
      if (invalid) {
        toast.error(`“${invalid}” is not a valid CIDR range (e.g. 10.0.0.0/8).`);
        return;
      }
    }
    save.mutate(draft);
  };

  if (current.isError) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-5">
        <p className="text-sm font-medium">We couldn&apos;t load security settings.</p>
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
          <div key={index} className="h-56 animate-pulse rounded-xl border bg-muted/40" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SecurityOverview />

      <SettingsSection
        id="authentication"
        title="Authentication"
        description="Requirements applied to every member signing in to this workspace."
        dirty={dirty}
        saving={save.isPending}
        onSave={saveChanges}
      >
        <FieldRow
          label="Require multi-factor authentication"
          hint="Members must configure an authenticator app before their next sign-in."
          control={
            <Switch
              checked={draft.mfaRequired}
              onCheckedChange={(checked) => update("mfaRequired", checked)}
              aria-label="Require multi-factor authentication"
            />
          }
        />

        <FieldRow
          label="Session timeout"
          hint="Idle sessions are signed out automatically."
          control={
            <div className="flex w-full items-center gap-3 sm:w-72">
              <Slider
                value={[draft.sessionTimeoutMinutes]}
                min={5}
                max={480}
                step={5}
                onValueChange={([value]) => update("sessionTimeoutMinutes", value ?? 60)}
                aria-label="Session timeout in minutes"
                className="flex-1"
              />
              <span className="w-16 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
                {draft.sessionTimeoutMinutes} min
              </span>
            </div>
          }
        />

        <FieldRow
          label="Single sign-on"
          hint="Members authenticate through your identity provider."
          control={
            <div className="flex items-center gap-3">
              <Select
                value={draft.ssoProvider}
                onValueChange={(value) => update("ssoProvider", value)}
                disabled={!draft.ssoEnabled}
              >
                <SelectTrigger className="w-40" aria-label="SSO provider">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["Okta", "Microsoft Entra ID", "Google Workspace", "JumpCloud"].map(
                    (provider) => (
                      <SelectItem key={provider} value={provider}>
                        {provider}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
              <Switch
                checked={draft.ssoEnabled}
                onCheckedChange={(checked) => update("ssoEnabled", checked)}
                aria-label="Enable single sign-on"
              />
            </div>
          }
        />
      </SettingsSection>

      <SettingsSection
        id="passwords"
        title="Password policy"
        description="Applies to password-based accounts only."
        dirty={dirty}
        saving={save.isPending}
        onSave={saveChanges}
      >
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="min-length">Minimum length</Label>
            <div className="flex items-center gap-2">
              <Input
                id="min-length"
                type="number"
                min={8}
                max={64}
                value={draft.minPasswordLength}
                onChange={(event) =>
                  update("minPasswordLength", Number(event.target.value) || 8)
                }
                className="w-20 text-right"
              />
              <span className="text-sm text-muted-foreground">characters</span>
            </div>
          </div>

          <FieldRow
            label="Require an uppercase letter"
            control={
              <Switch
                checked={draft.requireUppercase}
                onCheckedChange={(checked) => update("requireUppercase", checked)}
                aria-label="Require an uppercase letter"
              />
            }
          />
          <FieldRow
            label="Require a number"
            control={
              <Switch
                checked={draft.requireNumber}
                onCheckedChange={(checked) => update("requireNumber", checked)}
                aria-label="Require a number"
              />
            }
          />
        </div>
      </SettingsSection>

      <SettingsSection
        id="network"
        title="Network access"
        description="Restrict administrative access to trusted networks."
        dirty={dirty}
        saving={save.isPending}
        onSave={saveChanges}
      >
        <FieldRow
          label="IP allowlist"
          hint="One CIDR range per line. Applies to dashboard and API traffic."
          control={
            <Switch
              checked={draft.ipAllowlistEnabled}
              onCheckedChange={(checked) => update("ipAllowlistEnabled", checked)}
              aria-label="Enable IP allowlist"
            />
          }
        />

        <div className="space-y-2">
          <Label htmlFor="ip-allowlist">Allowed ranges</Label>
          <Textarea
            id="ip-allowlist"
            rows={4}
            disabled={!draft.ipAllowlistEnabled}
            value={draft.ipAllowlist.join("\n")}
            onChange={(event) =>
              update(
                "ipAllowlist",
                event.target.value.split("\n").filter((line) => line.trim().length > 0),
              )
            }
            placeholder={"10.0.0.0/8\n192.168.0.0/16"}
            className="font-mono text-xs"
          />
          <p className="text-xs text-muted-foreground">
            {draft.ipAllowlist.length} range{draft.ipAllowlist.length === 1 ? "" : "s"} configured
          </p>
        </div>
      </SettingsSection>
    </div>
  );
}
