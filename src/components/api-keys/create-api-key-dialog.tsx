"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Check, Copy, KeyRound, TriangleAlert } from "lucide-react";
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
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useCreateApiKey } from "@/lib/queries";
import { apiKeyPermissions } from "@/lib/mock/settings";
import { toast } from "sonner";

const schema = z.object({
  name: z.string().min(2, "Give the key a name"),
  environment: z.enum(["live", "test"]),
  expiration: z.enum(["never", "30", "90", "365"]),
  permissions: z.array(z.string()).min(1, "Select at least one permission"),
});

type FormValues = z.infer<typeof schema>;

interface CreateApiKeyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateApiKeyDialog({ open, onOpenChange }: CreateApiKeyDialogProps) {
  const create = useCreateApiKey();
  const [plaintext, setPlaintext] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      environment: "test",
      expiration: "90",
      permissions: ["documents:read", "collections:read"],
    },
  });

  const { handleSubmit, register, formState, reset, setValue, watch } = form;
  const environment = watch("environment");
  const permissions = watch("permissions");

  const close = (next: boolean) => {
    if (!next) {
      reset();
      setPlaintext(null);
      setCopied(false);
    }
    onOpenChange(next);
  };

  const onSubmit = (values: FormValues) => {
    create.mutate(values, {
      onSuccess: (result) => {
        setPlaintext(result.plaintext);
        toast.success("API key created.");
      },
      onError: (error) => toast.error(error.message || "Failed to create API key."),
    });
  };

  const copy = async () => {
    if (!plaintext) return;
    await navigator.clipboard.writeText(plaintext);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const togglePermission = (value: string) =>
    setValue(
      "permissions",
      permissions.includes(value)
        ? permissions.filter((item) => item !== value)
        : [...permissions, value],
      { shouldValidate: true },
    );

  if (plaintext) {
    return (
      <Dialog open={open} onOpenChange={close}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound className="h-4.5 w-4.5 text-primary" />
              Your API key
            </DialogTitle>
            <DialogDescription>Created with full scope for this environment.</DialogDescription>
          </DialogHeader>

          <Alert variant="destructive" className="border-warning/40 bg-warning/10 text-warning [&>svg]:text-warning">
            <TriangleAlert className="h-4 w-4" />
            <AlertTitle>Copy this key now. You won&apos;t be able to see it again.</AlertTitle>
            <AlertDescription className="text-warning/90">
              Store it in your secret manager. Rotating is recommended every 90 days.
            </AlertDescription>
          </Alert>

          <div className="flex items-center gap-2 rounded-lg border bg-muted/50 p-2.5">
            <code className="scrollbar-thin min-w-0 flex-1 overflow-x-auto whitespace-pre font-mono text-xs">
              {plaintext}
            </code>
            <Button size="sm" onClick={() => void copy()} className="shrink-0">
              {copied ? <Check className="mr-1.5 h-4 w-4" /> : <Copy className="mr-1.5 h-4 w-4" />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>

          <DialogFooter>
            <Button onClick={() => close(false)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Create API key</DialogTitle>
          <DialogDescription>
            Keys are scoped to this organization and can be revoked at any time.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="key-name">Name</Label>
            <Input id="key-name" placeholder="Production backend" {...register("name")} />
            {formState.errors.name ? (
              <p className="text-xs font-medium text-destructive" role="alert">
                {formState.errors.name.message}
              </p>
            ) : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Environment</Label>
              <Select
                value={environment}
                onValueChange={(value) =>
                  setValue("environment", value as FormValues["environment"], {
                    shouldValidate: true,
                  })
                }
              >
                <SelectTrigger aria-label="Environment">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="live">Production (sk_live_)</SelectItem>
                  <SelectItem value="test">Development (sk_test_)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Expiration</Label>
              <Select
                value={watch("expiration")}
                onValueChange={(value) =>
                  setValue("expiration", value as FormValues["expiration"], {
                    shouldValidate: true,
                  })
                }
              >
                <SelectTrigger aria-label="Expiration">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="never">Never expires</SelectItem>
                  <SelectItem value="30">30 days</SelectItem>
                  <SelectItem value="90">90 days</SelectItem>
                  <SelectItem value="365">1 year</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2.5 rounded-lg border p-3.5">
            <Label>Permissions</Label>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {apiKeyPermissions.map((permission) => (
                <label key={permission.value} className="flex items-center gap-2.5 text-sm">
                  <Checkbox
                    checked={permissions.includes(permission.value)}
                    onCheckedChange={() => togglePermission(permission.value)}
                  />
                  <span>{permission.label}</span>
                </label>
              ))}
            </div>
            {formState.errors.permissions ? (
              <p className="text-xs font-medium text-destructive" role="alert">
                {formState.errors.permissions.message}
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => close(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create key"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
