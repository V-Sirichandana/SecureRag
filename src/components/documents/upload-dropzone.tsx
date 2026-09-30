"use client";

import * as React from "react";
import { CheckCircle2, FileUp, RotateCw, UploadCloud, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn, formatBytes } from "@/lib/utils";
import { toast } from "sonner";

export type UploadStatus = "uploading" | "processing" | "complete" | "error" | "cancelled";

export interface UploadItem {
  id: string;
  name: string;
  size: number;
  progress: number;
  status: UploadStatus;
  error?: string;
}

const ACCEPTED_EXTENSIONS = ["pdf", "docx", "txt", "csv", "xlsx", "pptx", "md"];
export const acceptedFileTypes = ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(",");

export function isSupportedFile(name: string): boolean {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return ACCEPTED_EXTENSIONS.includes(ext);
}

interface UploadDropzoneProps {
  onUploaded?: (fileName: string) => void;
  className?: string;
}

export function UploadDropzone({ onUploaded, className }: UploadDropzoneProps) {
  const [items, setItems] = React.useState<UploadItem[]>([]);
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const timers = React.useRef(new Map<string, number>());

  React.useEffect(() => {
    const map = timers.current;
    return () => {
      map.forEach((timer) => window.clearInterval(timer));
      map.clear();
    };
  }, []);

  const patch = (id: string, next: Partial<UploadItem>) =>
    setItems((current) => current.map((item) => (item.id === id ? { ...item, ...next } : item)));

  const runUpload = React.useCallback(
    (item: UploadItem) => {
      patch(item.id, { status: "uploading", progress: 0, error: undefined });

      const timer = window.setInterval(() => {
        setItems((current) => {
          const target = current.find((entry) => entry.id === item.id);
          if (!target || target.status !== "uploading") return current;

          const nextProgress = Math.min(100, target.progress + 6 + Math.random() * 12);

          if (nextProgress >= 100) {
            window.clearInterval(timer);
            timers.current.delete(item.id);
            window.setTimeout(() => {
              patch(item.id, { status: "processing", progress: 100 });
              window.setTimeout(async () => {
                try {
                  patch(item.id, { status: "complete" });
                  toast.success(`“${item.name}” uploaded.`, {
                    description: "AI indexing has started.",
                  });
                  onUploaded?.(item.name);
                } catch {
                  patch(item.id, { status: "error", error: "Indexing failed" });
                }
              }, 1400);
            }, 0);
            return current.map((entry) =>
              entry.id === item.id ? { ...entry, progress: 100 } : entry,
            );
          }

          return current.map((entry) =>
            entry.id === item.id ? { ...entry, progress: nextProgress } : entry,
          );
        });
      }, 260);

      timers.current.set(item.id, timer);
    },
    [onUploaded],
  );

  const addFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const accepted: UploadItem[] = [];

    Array.from(fileList).forEach((file) => {
      if (!isSupportedFile(file.name)) {
        toast.error(`“${file.name}” isn’t a supported file type.`);
        return;
      }
      accepted.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        name: file.name,
        size: file.size,
        progress: 0,
        status: "uploading",
      });
    });

    if (!accepted.length) return;
    setItems((current) => [...accepted, ...current]);
    accepted.forEach((item) => runUpload(item));
  };

  const cancel = (item: UploadItem) => {
    const timer = timers.current.get(item.id);
    if (timer) window.clearInterval(timer);
    timers.current.delete(item.id);
    patch(item.id, { status: "cancelled", progress: 0 });
  };

  const retry = (item: UploadItem) => runUpload(item);

  const remove = (item: UploadItem) => {
    const timer = timers.current.get(item.id);
    if (timer) window.clearInterval(timer);
    timers.current.delete(item.id);
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
          PDF, DOCX, TXT, CSV, XLSX, PPTX and Markdown · up to 50 MB each
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
            Uploading documents
          </p>
          {items.map((item) => (
            <div key={item.id} className="rounded-lg border bg-card p-3">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-secondary">
                  {item.status === "complete" ? (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  ) : (
                    <FileUp className="h-4 w-4 text-muted-foreground" />
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

                  <p className="mt-1.5 text-xs text-muted-foreground">
                    {item.status === "uploading"
                      ? `${Math.round(item.progress)}% · uploading`
                      : item.status === "processing"
                        ? "100% · processing complete, indexing…"
                        : item.status === "complete"
                          ? "Processing complete"
                          : item.status === "cancelled"
                            ? "Upload cancelled"
                            : item.error ?? "Upload failed"}
                  </p>
                </div>

                <div className="flex shrink-0 items-center gap-1">
                  {item.status === "uploading" || item.status === "processing" ? (
                    <Button
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
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground"
                      onClick={() => retry(item)}
                      aria-label={`Retry upload of ${item.name}`}
                    >
                      <RotateCw className="h-4 w-4" />
                    </Button>
                  ) : null}
                  {item.status === "complete" ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground"
                      onClick={() => remove(item)}
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
    </div>
  );
}
