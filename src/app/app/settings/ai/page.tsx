"use client";

import * as React from "react";
import { Bot, FileCheck2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FieldRow, SettingsSection } from "@/components/settings/settings-section";
import { availableModels } from "@/lib/mock/settings";
import { useAISettings, useSaveAISettings } from "@/lib/queries";
import type { SettingsAI } from "@/lib/types";

export default function AISettingsPage() {
  const current = useAISettings();
  const save = useSaveAISettings();
  const [draft, setDraft] = React.useState<SettingsAI | null>(null);

  React.useEffect(() => {
    if (current.data) setDraft(current.data);
  }, [current.data]);

  const dirty = Boolean(
    draft && current.data && JSON.stringify(draft) !== JSON.stringify(current.data),
  );

  const update = <K extends keyof SettingsAI>(key: K, value: SettingsAI[K]) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  if (current.isError) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-5">
        <p className="text-sm font-medium">We couldn&apos;t load AI configuration.</p>
        <Button variant="outline" size="sm" onClick={() => void current.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 2 }).map((_, index) => (
          <div key={index} className="h-64 animate-pulse rounded-xl border bg-muted/40" />
        ))}
      </div>
    );
  }

  const selectedModel = availableModels.find((model) => model.value === draft.defaultModel);

  return (
    <div className="space-y-6">
      <Card className="gap-0 py-0 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Bot className="h-5 w-5" />
            </span>
            <div>
              <p className="text-sm font-semibold">{selectedModel?.label ?? draft.defaultModel}</p>
              <p className="text-xs text-muted-foreground">
                {selectedModel?.note ?? "Configured model"} · temperature {draft.temperature}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="text-muted-foreground">
              top-k {draft.retrievalTopK}
            </Badge>
            <Badge
              variant="outline"
              className={
                draft.requireCitations
                  ? "border-success/30 bg-success/10 text-success"
                  : "border-warning/30 bg-warning/10 text-warning"
              }
            >
              {draft.requireCitations ? "Citations enforced" : "Citations optional"}
            </Badge>
            <Badge variant="secondary">Demo data</Badge>
          </div>
        </CardContent>
      </Card>

      <SettingsSection
        id="model"
        title="Model"
        description="Default model used for chat answers and document summarization."
        dirty={dirty}
        saving={save.isPending}
        onSave={() => save.mutate(draft)}
      >
        <div className="space-y-2">
          <Label htmlFor="default-model">Default model</Label>
          <Select
            value={draft.defaultModel}
            onValueChange={(value) => update("defaultModel", value)}
          >
            <SelectTrigger id="default-model" aria-label="Default model">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {availableModels.map((model) => (
                <SelectItem key={model.value} value={model.value}>
                  <span className="flex flex-col">
                    <span>{model.label}</span>
                    <span className="text-xs text-muted-foreground">{model.note}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="temperature">Temperature</Label>
            <span className="text-sm tabular-nums text-muted-foreground">
              {draft.temperature.toFixed(1)}
            </span>
          </div>
          <Slider
            id="temperature"
            value={[draft.temperature]}
            min={0}
            max={1}
            step={0.1}
            onValueChange={([value]) => update("temperature", value ?? 0.2)}
            aria-label="Temperature"
          />
          <p className="text-xs text-muted-foreground">
            Lower values keep answers grounded in retrieved passages. Higher values allow more
            creative phrasing.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="max-tokens">Maximum response tokens</Label>
          <div className="flex items-center gap-2">
            <Input
              id="max-tokens"
              type="number"
              min={256}
              max={8192}
              step={256}
              value={draft.maxResponseTokens}
              onChange={(event) =>
                update("maxResponseTokens", Number(event.target.value) || 256)
              }
              className="w-32"
            />
            <span className="text-sm text-muted-foreground">tokens per answer</span>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        id="retrieval"
        title="Retrieval"
        description="How many passages are fetched and how they are ranked before generation."
        dirty={dirty}
        saving={save.isPending}
        onSave={() => save.mutate(draft)}
      >
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="top-k">Passages per query</Label>
            <span className="text-sm tabular-nums text-muted-foreground">
              top-{draft.retrievalTopK}
            </span>
          </div>
          <Slider
            id="top-k"
            value={[draft.retrievalTopK]}
            min={2}
            max={20}
            step={1}
            onValueChange={([value]) => update("retrievalTopK", value ?? 8)}
            aria-label="Passages per query"
          />
        </div>

        <FieldRow
          label="Reranking"
          hint="Score candidate passages with a cross-encoder after vector search."
          control={
            <div className="flex items-center gap-3">
              <RefreshCw className="hidden h-4 w-4 text-muted-foreground sm:block" />
              <Switch
                checked={draft.rerankingEnabled}
                onCheckedChange={(checked) => update("rerankingEnabled", checked)}
                aria-label="Enable reranking"
              />
            </div>
          }
        />

        <FieldRow
          label="Require citations"
          hint="Block answers that cannot be grounded in at least one source passage."
          control={
            <div className="flex items-center gap-3">
              <FileCheck2 className="hidden h-4 w-4 text-muted-foreground sm:block" />
              <Switch
                checked={draft.requireCitations}
                onCheckedChange={(checked) => update("requireCitations", checked)}
                aria-label="Require citations"
              />
            </div>
          }
        />
      </SettingsSection>
    </div>
  );
}
