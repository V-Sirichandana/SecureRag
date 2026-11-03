"use client";

import { FileText } from "lucide-react";
import { cn } from "@/lib/utils";

export function CitationChip({
  index,
  onClick,
  active,
}: {
  index: number;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Open source ${index}`}
      className={cn(
        "mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded border px-1 align-middle text-[10px] font-semibold leading-none transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-primary/40 bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground",
      )}
    >
      {index}
    </button>
  );
}

export function CitationSource({
  index,
  documentName,
  collectionName,
  pageNumber,
  quote,
  active,
  onClick,
}: {
  index: number;
  documentName: string;
  collectionName: string;
  pageNumber: number;
  quote: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors",
        active ? "border-primary/50 bg-primary/5" : "hover:border-primary/40 hover:bg-muted/50",
      )}
      aria-label={`Open ${documentName}, page ${pageNumber}`}
    >
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-[11px] font-semibold text-primary">
        {index}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{documentName}</span>
        </span>
        <span className="mt-0.5 block text-xs text-muted-foreground">
          {collectionName ? `${collectionName} · ` : ""}Page {pageNumber}
        </span>
        <span className="mt-1 line-clamp-2 block text-xs italic text-muted-foreground/80">
          “{quote}”
        </span>
      </span>
    </button>
  );
}
