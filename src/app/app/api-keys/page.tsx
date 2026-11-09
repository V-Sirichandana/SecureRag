"use client";

import * as React from "react";
import { toast } from "sonner";
import { Clock, Copy, KeyRound, MoreHorizontal, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { CreateApiKeyDialog } from "@/components/api-keys/create-api-key-dialog";
import { useApiKeys, useRevokeApiKey } from "@/lib/queries";
import { formatDate, timeAgo } from "@/lib/utils";
import type { ApiKey } from "@/lib/types";

export default function ApiKeysPage() {
  const [open, setOpen] = React.useState(false);
  const [pendingRevoke, setPendingRevoke] = React.useState<ApiKey | null>(null);
  const keys = useApiKeys();
  const revoke = useRevokeApiKey();

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="API Keys"
        description="Programmatic access to search, chat and document endpoints for your applications."
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Create API Key
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-success" />
          Keys are shown once at creation
        </Badge>
        <Badge variant="outline" className="text-muted-foreground">
          {(keys.data ?? []).length} active keys
        </Badge>
      </div>

      {keys.isError ? (
        <ErrorState
          title="We couldn't load your API keys"
          description="The credentials service didn't respond."
          onRetry={() => void keys.refetch()}
        />
      ) : keys.isPending ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <div key={index} className="h-44 animate-pulse rounded-xl border bg-muted/40" />
          ))}
        </div>
      ) : keys.data?.length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="No API keys yet"
          description="Create a key to call SecureRAG from your services. Keys are scoped to this organization."
          action={<Button onClick={() => setOpen(true)}>Create API key</Button>}
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {keys.data?.map((key) => (
            <Card key={key.id} className="gap-0 py-0">
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                        key.environment === "live"
                          ? "bg-primary/10 text-primary"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <KeyRound className="h-4.5 w-4.5" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold">{key.name}</p>
                        <Badge
                          variant="outline"
                          className={
                            key.environment === "live"
                              ? "border-primary/30 bg-primary/10 text-primary"
                              : "text-muted-foreground"
                          }
                        >
                          {key.environment === "live" ? "Production" : "Development"}
                        </Badge>
                      </div>
                      <code className="mt-1.5 block font-mono text-xs text-muted-foreground">
                        {key.maskedKey}
                      </code>
                    </div>
                  </div>

                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0 text-muted-foreground"
                        aria-label={`Actions for ${key.name}`}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-44">
                      <DropdownMenuItem
                        onClick={() => {
                          void navigator.clipboard.writeText(key.maskedKey);
                          toast.info("Masked value copied. The full key is not recoverable.");
                        }}
                      >
                        <Copy className="mr-2 h-4 w-4" />
                        Copy masked value
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => toast.success("Rotation scheduled.")}>
                        Rotate key
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-destructive focus:text-destructive"
                        onClick={() => setPendingRevoke(key)}
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        Revoke key
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                <dl className="mt-4 grid grid-cols-2 gap-3 border-t pt-3 text-xs">
                  <div>
                    <dt className="text-muted-foreground">Created</dt>
                    <dd className="mt-0.5 font-medium">{formatDate(key.createdAt)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Last used</dt>
                    <dd className="mt-0.5 font-medium">
                      {key.lastUsedAt ? timeAgo(key.lastUsedAt) : "Never used"}
                    </dd>
                  </div>
                </dl>

                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  {key.expiresAt ? (
                    <Badge variant="outline" className="gap-1 text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      Expires {formatDate(key.expiresAt)}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      No expiration
                    </Badge>
                  )}
                  {key.permissions.map((permission) => (
                    <Badge key={permission} variant="secondary" className="font-mono text-[10px]">
                      {permission}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <CreateApiKeyDialog open={open} onOpenChange={setOpen} />

      <AlertDialog
        open={Boolean(pendingRevoke)}
        onOpenChange={(openState) => {
          if (!openState) setPendingRevoke(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke “{pendingRevoke?.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              Any integration using this key will start receiving 401 responses immediately. This
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={(event) => {
                event.preventDefault();
                if (!pendingRevoke) return;
                revoke.mutate(pendingRevoke.id, {
                  onSuccess: () => setPendingRevoke(null),
                });
              }}
            >
              Revoke key
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
