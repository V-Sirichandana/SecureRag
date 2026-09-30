"use client";

import * as React from "react";
import { toast } from "sonner";
import { Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { FieldRow, SettingsSection } from "@/components/settings/settings-section";
import { useBillingSettings, useInvoices, useSaveBillingSettings } from "@/lib/queries";
import { formatDate } from "@/lib/utils";
import type { SettingsBilling } from "@/lib/types";

export default function BillingSettingsPage() {
  const current = useBillingSettings();
  const invoices = useInvoices();
  const save = useSaveBillingSettings();
  const [draft, setDraft] = React.useState<SettingsBilling | null>(null);

  React.useEffect(() => {
    if (current.data) setDraft(current.data);
  }, [current.data]);

  const dirty = Boolean(
    draft && current.data && JSON.stringify(draft) !== JSON.stringify(current.data),
  );

  const update = <K extends keyof SettingsBilling>(key: K, value: SettingsBilling[K]) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  if (current.isError) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-5">
        <p className="text-sm font-medium">We couldn&apos;t load billing settings.</p>
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

  const saveChanges = () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.billingEmail)) {
      toast.error("Enter a valid billing email address.");
      return;
    }
    save.mutate(draft);
  };

  const seatPercent = Math.min(100, Math.round((draft.seatsUsed / draft.seatsTotal) * 100));
  const storagePercent = Math.min(
    100,
    Math.round((draft.storageUsedGb / draft.storageTotalGb) * 100),
  );

  return (
    <div className="space-y-6">
      <SettingsSection
        id="plan"
        title="Current plan"
        description="Subscription status and included capacity for this organization."
        footer={
          <Button
            variant="outline"
            onClick={() => toast.info("Plan changes require a connected billing backend.")}
          >
            Change plan
          </Button>
        }
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold">{draft.planName}</span>
              <Badge
                variant="outline"
                className="border-success/30 bg-success/10 font-medium text-success"
              >
                Active
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {draft.planPrice} · Renews {formatDate(draft.renewsAt)}
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-sm">
              <span>Seats</span>
              <span className="tabular-nums text-muted-foreground">
                {draft.seatsUsed} of {draft.seatsTotal} used
              </span>
            </div>
            <Progress value={seatPercent} aria-label="Seat usage" />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-sm">
              <span>Storage</span>
              <span className="tabular-nums text-muted-foreground">
                {draft.storageUsedGb} GB of {draft.storageTotalGb} GB
              </span>
            </div>
            <Progress value={storagePercent} aria-label="Storage usage" />
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        id="billing-details"
        title="Billing details"
        description="Where invoices are sent and how the subscription renews."
        dirty={dirty}
        saving={save.isPending}
        onSave={saveChanges}
        footer={
          <span className="mr-auto text-xs text-muted-foreground">
            {dirty ? "You have unsaved changes" : "All changes saved"}
          </span>
        }
      >
        <div className="space-y-2">
          <Label htmlFor="billing-email">Billing email</Label>
          <Input
            id="billing-email"
            type="email"
            value={draft.billingEmail}
            onChange={(event) => update("billingEmail", event.target.value)}
            placeholder="finance@example.com"
          />
        </div>

        <FieldRow
          label="Invoice delivery"
          hint="Emailed with the invoice or pushed to the billing portal."
          control={
            <Select
              value={draft.invoiceDelivery}
              onValueChange={(value) =>
                update("invoiceDelivery", value as SettingsBilling["invoiceDelivery"])
              }
            >
              <SelectTrigger className="w-44" aria-label="Invoice delivery">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="email">Email</SelectItem>
                <SelectItem value="portal">Billing portal</SelectItem>
              </SelectContent>
            </Select>
          }
        />

        <div className="space-y-2">
          <Label htmlFor="po-number">Purchase order number</Label>
          <Input
            id="po-number"
            value={draft.purchaseOrderNumber}
            onChange={(event) => update("purchaseOrderNumber", event.target.value)}
            placeholder="Optional — printed on invoices"
          />
        </div>

        <FieldRow
          label="Auto-renew"
          hint="Renew automatically at the end of the billing period."
          control={
            <Switch
              checked={draft.autoRenew}
              onCheckedChange={(checked) => update("autoRenew", checked)}
              aria-label="Auto-renew"
            />
          }
        />
      </SettingsSection>

      <SettingsSection
        id="invoices"
        title="Invoice history"
        description="Past invoices for this organization."
      >
        {invoices.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="h-10 animate-pulse rounded-md bg-muted/40" />
            ))}
          </div>
        ) : invoices.isError ? (
          <div className="flex flex-col items-start gap-3">
            <p className="text-sm font-medium">We couldn&apos;t load invoices.</p>
            <Button variant="outline" size="sm" onClick={() => void invoices.refetch()}>
              Try again
            </Button>
          </div>
        ) : !invoices.data?.length ? (
          <p className="text-sm text-muted-foreground">No invoices yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Invoice</TableHead>
                <TableHead>Issued</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Receipt</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoices.data.map((invoice) => (
                <TableRow key={invoice.id}>
                  <TableCell className="font-medium">{invoice.number}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(invoice.issuedAt)}
                  </TableCell>
                  <TableCell className="tabular-nums">{invoice.amount}</TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={
                        invoice.status === "paid"
                          ? "border-success/30 bg-success/10 font-medium text-success"
                          : "border-border bg-muted font-medium text-muted-foreground"
                      }
                    >
                      {invoice.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Download ${invoice.number}`}
                      onClick={() =>
                        toast.info("Receipts require a connected billing backend.")
                      }
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SettingsSection>
    </div>
  );
}
