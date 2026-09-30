"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Download, ExternalLink, Minus, Plus, X } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/common/skeletons";
import { ErrorState } from "@/components/common/error-state";
import { useDocument, useDocumentPages } from "@/lib/queries";
import { cn } from "@/lib/utils";
import type { Citation } from "@/lib/types";

interface SourcePreviewProps {
  citation: Citation | null;
  onOpenChange: (open: boolean) => void;
}

export function SourcePreview({ citation, onOpenChange }: SourcePreviewProps) {
  const router = useRouter();
  const documentId = citation?.documentId ?? "";
  const pages = useDocumentPages(documentId, Boolean(citation));
  const document = useDocument(documentId);
  const [pageIndex, setPageIndex] = React.useState(0);
  const [zoom, setZoom] = React.useState(100);

  React.useEffect(() => {
    if (!citation || !pages.data) return;
    const target = pages.data.findIndex((page) => page.pageNumber === citation.pageNumber);
    setPageIndex(target >= 0 ? target : 0);
    setZoom(100);
  }, [citation, pages.data]);

  const list = pages.data ?? [];
  const currentPage = list[pageIndex];

  const move = (delta: number) =>
    setPageIndex((current) => Math.min(Math.max(current + delta, 0), list.length - 1));

  return (
    <Sheet open={Boolean(citation)} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 p-0 sm:max-w-xl"
        aria-label="Document source preview"
      >
        <SheetHeader className="border-b px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <SheetTitle className="truncate text-base">
                {document.data?.name ?? citation?.documentName ?? "Source"}
              </SheetTitle>
              <SheetDescription className="mt-1">
                {citation ? `Page ${citation.pageNumber} · ${citation.collectionName}` : ""}
              </SheetDescription>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => toast.success("Download started.")}
                aria-label="Download document"
              >
                <Download className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  onOpenChange(false);
                  router.push(`/app/documents/${documentId}`);
                }}
                aria-label="Open full document"
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </SheetHeader>

        <div className="flex items-center justify-between gap-3 border-b bg-muted/30 px-5 py-2.5">
          <div className="flex items-center gap-1.5">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => move(-1)}
              disabled={pageIndex <= 0}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="min-w-24 text-center text-xs tabular-nums text-muted-foreground">
              {list.length ? `${pageIndex + 1} of ${list.length}` : "—"}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => move(1)}
              disabled={pageIndex >= list.length - 1}
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setZoom((value) => Math.max(70, value - 10))}
              aria-label="Zoom out"
            >
              <Minus className="h-4 w-4" />
            </Button>
            <span className="w-10 text-center text-xs tabular-nums text-muted-foreground">
              {zoom}%
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setZoom((value) => Math.min(160, value + 10))}
              aria-label="Zoom in"
            >
              <Plus className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onOpenChange(false)}
              aria-label="Close source preview"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="scrollbar-thin flex-1 overflow-y-auto bg-muted/20 p-5">
          {pages.isPending ? (
            <div className="space-y-3">
              <Skeleton className="h-8 w-2/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-4/5" />
              <Skeleton className="h-4 w-full" />
            </div>
          ) : pages.isError ? (
            <ErrorState
              title="Preview unavailable"
              description="We couldn't load this page. Try opening the full document instead."
              onRetry={() => void pages.refetch()}
            />
          ) : currentPage ? (
            <article
              className="mx-auto max-w-prose rounded-lg border bg-card p-6 shadow-sm transition-[font-size]"
              style={{ fontSize: `${(zoom / 100) * 14}px` }}
            >
              <div className="mb-4 flex items-center justify-between border-b pb-3">
                <h3 className="font-semibold">{currentPage.title}</h3>
                <Badge variant="outline" className="shrink-0 text-muted-foreground">
                  Page {currentPage.pageNumber}
                </Badge>
              </div>
              <div className="space-y-4 leading-relaxed text-muted-foreground">
                {currentPage.paragraphs.map((paragraph) => (
                  <p key={paragraph.id}>
                    {paragraph.highlight ? (
                      <>
                        {paragraph.text.split(paragraph.highlight).map((part, index, all) => (
                          <React.Fragment key={index}>
                            {part}
                            {index < all.length - 1 ? (
                              <mark className="rounded bg-warning/30 px-0.5 text-foreground">
                                {paragraph.highlight}
                              </mark>
                            ) : null}
                          </React.Fragment>
                        ))}
                      </>
                    ) : (
                      paragraph.text
                    )}
                  </p>
                ))}
              </div>
              <p className={cn("mt-6 border-t pt-3 text-[0.7em] text-muted-foreground/70")}>
                Highlighted passages were used to ground the assistant&apos;s answer.
              </p>
            </article>
          ) : (
            <p className="text-center text-sm text-muted-foreground">No pages available.</p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
