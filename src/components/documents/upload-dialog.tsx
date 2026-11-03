"use client";

import * as React from "react";
import { FolderPlus, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { UploadDropzone } from "@/components/documents/upload-dropzone";
import { useCollections } from "@/lib/queries";
import {
  getCollectionReadiness,
  type CollectionLoadState,
} from "@/lib/upload-workflow";
import type { Classification } from "@/lib/types";

interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded?: (name: string) => void;
}

export function UploadDialog({ open, onOpenChange, onUploaded }: UploadDialogProps) {
  const collections = useCollections();
  const [collectionId, setCollectionId] = React.useState("");
  const [classification, setClassification] = React.useState<Classification>("internal");

  const collectionsState: CollectionLoadState = collections.isPending
    ? "loading"
    : collections.isError
      ? "error"
      : "ready";
  const collectionCount = collections.data?.length ?? 0;
  const collectionReadiness = getCollectionReadiness({
    state: collectionsState,
    collectionCount,
    collectionId,
  });
  const collectionSelectionDisabled =
    collectionsState !== "ready" || collectionCount === 0;

  React.useEffect(() => {
    if (
      collections.isSuccess &&
      collectionId &&
      !collections.data.some((collection) => collection.id === collectionId)
    ) {
      setCollectionId("");
    }
  }, [collections.isSuccess, collections.data, collectionId]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Upload documents</DialogTitle>
          <DialogDescription>
            Files are indexed into the selected collection and become searchable with citations.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="upload-collection">Collection</Label>
            <Select
              value={collectionId || undefined}
              onValueChange={setCollectionId}
              disabled={collectionSelectionDisabled}
            >
              <SelectTrigger id="upload-collection" aria-label="Destination collection">
                <SelectValue placeholder="Select a collection" />
              </SelectTrigger>
              <SelectContent>
                {collections.data?.map((collection) => (
                  <SelectItem key={collection.id} value={collection.id}>
                    {collection.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {collectionsState === "loading" ? (
              <p
                className="flex items-center gap-1.5 text-xs text-muted-foreground"
                role="status"
                aria-live="polite"
              >
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading collections…
              </p>
            ) : collectionsState === "error" ? (
              <div className="space-y-1" role="alert">
                <p className="text-xs text-destructive">
                  {collections.error?.message || "Collections could not be loaded."}
                </p>
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-xs"
                  onClick={() => void collections.refetch()}
                >
                  Retry loading collections
                </Button>
              </div>
            ) : collectionReadiness.message ? (
              <p
                className={
                  collectionReadiness.code === "invalid"
                    ? "text-xs text-destructive"
                    : "text-xs text-muted-foreground"
                }
                role={
                  collectionReadiness.code === "empty" ||
                  collectionReadiness.code === "invalid"
                    ? "alert"
                    : "status"
                }
                aria-live="polite"
              >
                {collectionReadiness.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="upload-classification">Classification</Label>
            <Select
              value={classification}
              onValueChange={(value) => setClassification(value as Classification)}
            >
              <SelectTrigger id="upload-classification" aria-label="Document classification">
                <SelectValue placeholder="Select classification" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="public">Public</SelectItem>
                <SelectItem value="internal">Internal</SelectItem>
                <SelectItem value="confidential">Confidential</SelectItem>
                <SelectItem value="restricted">Restricted</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <UploadDropzone
          collectionId={collectionId}
          collectionsState={collectionsState}
          collectionCount={collectionCount}
          classification={classification}
          onUploaded={onUploaded}
        />

        <div className="flex items-center justify-between gap-3 border-t pt-4">
          <p className="text-xs text-muted-foreground">
            Access inherits the collection&apos;s permissions.
          </p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
            <Button onClick={() => onOpenChange(false)}>
              <FolderPlus className="mr-2 h-4 w-4" />
              Done
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
