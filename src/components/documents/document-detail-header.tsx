"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, Download, MessageSquareQuote, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/common/skeletons";
import { ErrorState } from "@/components/common/error-state";
import { DocumentStatusBadge, ClassificationBadge } from "@/components/common/status-badge";
import { useDocument, useDeleteDocument } from "@/lib/queries";
import { formatBytes, formatDate, formatNumber, timeAgo } from "@/lib/utils";

export function DocumentDetailHeader({ id }: { id: string }) {
  const router = useRouter();
  const { data, isPending, isError, refetch } = useDocument(id);
  const deleteDocument = useDeleteDocument();

  if (isPending) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-4 w-96" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <ErrorState
        variant="not-found"
        title="Document not found"
        description="The document may have been deleted or you may not have permission to access it."
        action={
          <Button variant="outline" onClick={() => router.push("/app/documents")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Documents
          </Button>
        }
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="space-y-4">
      <Button
        variant="ghost"
        size="sm"
        className="-ml-2 text-muted-foreground"
        onClick={() => router.push("/app/documents")}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        All documents
      </Button>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-balance">{data.name}</h1>
            <DocumentStatusBadge status={data.status} />
            <ClassificationBadge value={data.classification} />
          </div>
          <p className="text-sm text-muted-foreground">
            {data.fileType.toUpperCase()} · {formatBytes(data.sizeBytes)} · owned by {data.owner} ·
            updated {timeAgo(data.updatedAt)}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {data.tags.map((tag) => (
              <Badge key={tag} variant="secondary" className="font-normal">
                {tag}
              </Badge>
            ))}
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          <Button variant="outline" onClick={() => toast.success("Download started.")}>
            <Download className="mr-2 h-4 w-4" />
            Download
          </Button>
          <Button onClick={() => router.push(`/app/chat?document=${data.id}`)}>
            <MessageSquareQuote className="mr-2 h-4 w-4" />
            Ask about this
          </Button>
          <Button
            variant="outline"
            className="text-destructive hover:bg-destructive/10"
            onClick={() =>
              deleteDocument.mutate(data.id, {
                onSuccess: () => {
                  toast.success(`“${data.name}” deleted.`);
                  router.push("/app/documents");
                },
              })
            }
            disabled={deleteDocument.isPending}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      <dl className="grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Meta label="File type" value={data.fileType.toUpperCase()} />
        <Meta label="Size" value={formatBytes(data.sizeBytes)} />
        <Meta label="Owner" value={data.owner} />
        <Meta label="Collection" value={data.collectionName} />
        <Meta label="Created" value={formatDate(data.createdAt)} />
        <Meta label="Updated" value={formatDate(data.updatedAt)} />
        <Meta label="Pages" value={formatNumber(data.pageCount)} />
        <Meta label="Indexed chunks" value={formatNumber(data.chunkCount)} />
      </dl>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm font-medium">{value}</dd>
    </div>
  );
}
