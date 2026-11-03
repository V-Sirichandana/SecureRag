"use client";

import * as React from "react";
import {
  CheckCircle2,
  FileUp,
  Loader2,
  RotateCw,
  UploadCloud,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn, formatBytes } from "@/lib/utils";
import { toast } from "sonner";
import { uploadDocumentFile } from "@/lib/api/documents";
import {
  acceptedFileTypes,
  getUploadErrorMessage,
  getUploadOutcome,
  getUploadReadiness,
  isSupportedFile,
  isWithinUploadSizeLimit,
  MAX_UPLOAD_BYTES,
  type CollectionLoadState,
} from "@/lib/upload-workflow";
import type { Classification } from "@/lib/types";

export type UploadStatus =
  | "queued"
  | "uploading"
  | "finalizing"
  | "processing"
  | "complete"
  | "error"
  | "cancelled";

export interface UploadItem {
  id: string;
  file: File;
  name: string;
  size: number;
  progress: number;
  status: UploadStatus;
  error?: string;
  message?: string;
}

interface UploadDropzoneProps {
  collectionId: string;
  collectionsState: CollectionLoadState;
  collectionCount: number;
  classification: Classification;
  onUploaded?: (fileName: string) => void;
  className?: string;
}

function itemStatusText(item: UploadItem): string {
  switch (item.status) {
    case "queued":
      return "Ready to upload";
    case "uploading":
      return `${Math.round(item.progress)}% · uploading`;
    case "finalizing":
      return "Upload sent · waiting for the server to finish indexing";
    case "processing":
      return item.message ?? "Upload accepted · indexing is still in progress";
    case "complete":
      return item.message ?? "Stored, indexed and ready to search.";
    case "cancelled":
      return "Upload cancelled";
    case "error":
      return item.error ?? "Upload failed";
  }
}

export function UploadDropzone({
  collectionId,
  collectionsState,
  collectionCount,
  classification,
  onUploaded,
  className,
}: UploadDropzoneProps) {
  const [items, setItems] = React.useState<UploadItem[]>([]);
  const [dragging, setDragging] = React.useState(false);
  const [isUploading, setIsUploading] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const aborts = React.useRef(new Map<string, AbortController>());
  const uploadingRef = React.useRef(false);

  React.useEffect(() => {
    const map = aborts.current;
    return () => {
      map.forEach((controller) => controller.abort());
      map.clear();
    };
  }, []);

  const patch = React.useCallback(
    (id: string, next: Partial<UploadItem>) =>
      setItems((current) =>
        current.map((item) => (item.id === id ? { ...item, ...next } : item)),
      ),
    [],
  );

  const runUpload = React.useCallback(
    async (item: UploadItem, destinationId: string, destinationClassification: Classification) => {
      const controller = new AbortController();
      aborts.current.set(item.id, controller);
      patch(item.id, {
        status: "uploading",
        progress: 0,
        error: undefined,
        message: undefined,
      });

      try {
        const document = await uploadDocumentFile({
          file: item.file,
          collectionId: destinationId,
          classification: destinationClassification,
          signal: controller.signal,
          onProgress: (fraction) => {
            const progress = Math.min(100, Math.round(fraction * 100));
            patch(
              item.id,
              progress >= 100
                ? { progress, status: "finalizing" }
                : { progress },
            );
          },
        });

        const outcome = getUploadOutcome(document);
        if (outcome.kind === "success") {
          patch(item.id, {
            status: "complete",
            progress: 100,
            message: outcome.message,
          });
          toast.success(`“${item.name}” uploaded and indexed.`, {
            description: outcome.message,
          });
          onUploaded?.(item.name);
        } else if (outcome.kind === "processing") {
          patch(item.id, {
            status: "processing",
            progress: 100,
            message: outcome.message,
          });
          toast.info(`“${item.name}” was uploaded.`, {
            description: outcome.message,
          });
        } else {
          patch(item.id, {
            status: "error",
            progress: 100,
            error: outcome.message,
          });
          toast.error(`“${item.name}” could not be indexed.`, {
            description: outcome.message,
          });
        }
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") {
          patch(item.id, { status: "cancelled", progress: 0 });
          return;
        }
        const message = getUploadErrorMessage(error);
        patch(item.id, { status: "error", error: message });
        toast.error(`“${item.name}” failed to upload.`, { description: message });
      } finally {
        aborts.current.delete(item.id);
      }
    },
    [onUploaded, patch],
  );

  const queuedItems = items.filter((item) => item.status === "queued");

  const uploadReadiness = getUploadReadiness({
    collectionsState,
    collectionCount,
    collectionId,
    fileCount: queuedItems.length,
    isUploading,
  });
  const retryReadiness = getUploadReadiness({
    collectionsState,
    collectionCount,
    collectionId,
    fileCount: 1,
    isUploading: false,
  });

  const startUploads = async (targets: UploadItem[]) => {
    if (!targets.length || uploadingRef.current) return;

    const readiness = getUploadReadiness({
      collectionsState,
      collectionCount,
      collectionId,
      fileCount: targets.length,
      isUploading: false,
    });
    if (!readiness.ready) {
      if (readiness.message) toast.error(readiness.message);
      return;
    }

    uploadingRef.current = true;
    setIsUploading(true);

    try {
      for (const target of targets) {
        await runUpload(target, collectionId, classification);
      }
    } finally {
      uploadingRef.current = false;
      setIsUploading(false);
    }
  };

  const addFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const accepted: UploadItem[] = [];

    Array.from(fileList).forEach((file) => {
      if (!isSupportedFile(file.name)) {
        toast.error(`“${file.name}” isn’t a supported file type.`);
        return;
      }
      if (file.size === 0) {
        toast.error(`“${file.name}” is empty and cannot be uploaded.`);
        return;
      }
      if (!isWithinUploadSizeLimit(file.size)) {
        toast.error(
          `“${file.name}” exceeds the ${formatBytes(MAX_UPLOAD_BYTES, 0)} upload limit.`,
        );
        return;
      }
      accepted.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        file,
        name: file.name,
        size: file.size,
        progress: 0,
        status: "queued",
      });
    });

    if (accepted.length) {
      setItems((current) => [...accepted, ...current]);
    }
  };

  const cancel = (item: UploadItem) => {
    aborts.current.get(item.id)?.abort();
  };

  const retry = (item: UploadItem) => {
    void startUploads([item]);
  };

  const remove = (item: UploadItem) => {
    aborts.current.get(item.id)?.abort();
    aborts.current.delete(item.id);
    setItems((current) => current.filter((entry) => entry.id !== item.id));
  };

  return (
    <div className={cn("space-y-4", className)}>
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload documents by drag and drop or browse"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          dragging
            ? "border-primary bg-primary/5"
            : "border-border bg-muted/20 hover:border-primary/50 hover:bg-muted/40",
        )}
      >
        <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 text-primary">
          <UploadCloud className="h-5 w-5" />
        </span>
        <p className="text-sm font-medium">
          Drop files here or <span className="text-primary">browse</span>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          PDF, DOCX, TXT, CSV and Markdown · up to {formatBytes(MAX_UPLOAD_BYTES, 0)} each
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={acceptedFileTypes}
          className="hidden"
          aria-hidden="true"
          tabIndex={-1}
          onChange={(event) => {
            addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {items.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Files
          </p>
          {items.map((item) => (
            <div key={item.id} className="rounded-lg border bg-card p-3">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-secondary">
                  {item.status === "complete" ? (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  ) : (
                    <FileUp
                      className={cn(
                        "h-4 w-4",
                        item.status === "error"
                          ? "text-destructive"
                          : "text-muted-foreground",
                      )}
                    />
                  )}
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="truncate text-sm font-medium">{item.name}</p>
                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                      {formatBytes(item.size)}
                    </span>
                  </div>

                  <div className="mt-2">
                    <Progress
                      value={item.progress}
                      className="h-1.5"
                      aria-label={`${item.name} upload progress`}
                    />
                  </div>

                  <p
                    className={cn(
                      "mt-1.5 text-xs",
                      item.status === "error"
                        ? "text-destructive"
                        : "text-muted-foreground",
                    )}
                    role={item.status === "error" ? "alert" : "status"}
                  >
                    {itemStatusText(item)}
                  </p>
                </div>

                <div className="flex shrink-0 items-center gap-1">
                  {item.status === "uploading" || item.status === "finalizing" ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground"
                      onClick={() => cancel(item)}
                      aria-label={`Cancel upload of ${item.name}`}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  ) : null}
                  {item.status === "error" || item.status === "cancelled" ? (
                    <>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground"
                        onClick={() => retry(item)}
                        disabled={isUploading || !retryReadiness.ready}
                        aria-label={`Retry upload of ${item.name}`}
                      >
                        <RotateCw className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground"
                        onClick={() => remove(item)}
                        disabled={isUploading}
                        aria-label={`Remove ${item.name} from the list`}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </>
                  ) : null}
                  {item.status === "queued" ||
                  item.status === "complete" ||
                  item.status === "processing" ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground"
                      onClick={() => remove(item)}
                      disabled={isUploading && item.status === "queued"}
                      aria-label={`Remove ${item.name} from the list`}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p
          className="text-xs text-muted-foreground"
          role="status"
          aria-live="polite"
        >
          {isUploading
            ? "Uploading. Keep this dialog open until the files finish."
            : uploadReadiness.message ??
              `${queuedItems.length} file${queuedItems.length === 1 ? "" : "s"} ready to upload.`}
        </p>
        <Button
          type="button"
          onClick={() => void startUploads(queuedItems)}
          disabled={!uploadReadiness.ready}
          aria-busy={isUploading}
        >
          {isUploading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <UploadCloud className="mr-2 h-4 w-4" />
          )}
          {isUploading
            ? "Uploading…"
            : queuedItems.length > 0
              ? `Upload ${queuedItems.length} file${queuedItems.length === 1 ? "" : "s"}`
              : "Upload"}
        </Button>
      </div>
    </div>
  );
}
