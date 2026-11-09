"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { FileText, FolderPlus, Upload } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import {
  DocumentFilters,
  emptyFilterState,
  type DocumentFilterState,
} from "@/components/documents/document-filters";
import { DocumentTable } from "@/components/documents/document-table";
import { UploadDialog } from "@/components/documents/upload-dialog";
import { CreateCollectionDialog } from "@/components/collections/create-collection-dialog";
import {
  useCollections,
  useDeleteDocument,
  useDocuments,
  useUpdateDocument,
} from "@/lib/queries";
import { useDebounce } from "@/hooks/use-client";
import { DEMO_NOTICE } from "@/lib/mock/utils";
import type { DocumentRecord } from "@/lib/types";
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

export default function DocumentsPage() {
  return (
    <React.Suspense
      fallback={
        <div className="mx-auto w-full max-w-[1500px] space-y-5 p-4 sm:p-6 lg:p-8">
          <div className="h-9 w-40 animate-pulse rounded-md bg-muted" />
          <div className="h-28 w-full animate-pulse rounded-xl bg-muted" />
          <div className="h-96 w-full animate-pulse rounded-xl bg-muted" />
        </div>
      }
    >
      <DocumentsContent />
    </React.Suspense>
  );
}

function DocumentsContent() {
  const searchParams = useSearchParams();
  const initialCollection = searchParams.get("collection") ?? "all";

  const [filters, setFilters] = React.useState<DocumentFilterState>({
    ...emptyFilterState,
    collectionId: initialCollection,
  });
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [collectionDialogOpen, setCollectionDialogOpen] = React.useState(false);
  const [pendingDelete, setPendingDelete] = React.useState<DocumentRecord | null>(null);

  const debouncedSearch = useDebounce(filters.search, 300);
  const collections = useCollections();

  const queryFilters = {
    search: debouncedSearch || undefined,
    collectionId: filters.collectionId,
    department: filters.department,
    classification: filters.classification,
    fileType: filters.fileType,
    status: filters.status,
  };

  const documents = useDocuments(queryFilters);
  const deleteDocument = useDeleteDocument();
  const updateDocument = useUpdateDocument();

  const applyDateFilter = (list: DocumentRecord[]) => {
    if (filters.uploaded === "any") return list;
    const windowMs =
      filters.uploaded === "24h"
        ? 86_400_000
        : filters.uploaded === "7d"
          ? 7 * 86_400_000
          : 30 * 86_400_000;
    const cutoff = Date.now() - windowMs;
    return list.filter((doc) => new Date(doc.createdAt).getTime() >= cutoff);
  };

  const visibleDocuments = applyDateFilter(documents.data ?? []);

  const handleDelete = () => {
    if (!pendingDelete) return;
    deleteDocument.mutate(pendingDelete.id, {
      onSuccess: () => {
        toast.success(`“${pendingDelete.name}” deleted.`);
        setPendingDelete(null);
      },
      onError: (error) => toast.error(error.message || "Failed to delete document."),
    });
  };

  const handleArchive = (document: DocumentRecord) => {
    updateDocument.mutate(
      [document.id, { status: "archived" }],
      { onSuccess: () => toast.success(`“${document.name}” archived.`) },
    );
  };

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-5 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Documents"
        description="Upload, classify and control access to your organization's knowledge."
        actions={
          <>
            <Button variant="outline" onClick={() => setCollectionDialogOpen(true)}>
              <FolderPlus className="mr-2 h-4 w-4" />
              New collection
            </Button>
            <Button onClick={() => setUploadOpen(true)}>
              <Upload className="mr-2 h-4 w-4" />
              Upload documents
            </Button>
          </>
        }
      />

      <DocumentFilters
        value={filters}
        onChange={setFilters}
        collections={collections.data ?? []}
      />

      <div className="overflow-hidden rounded-xl border bg-card">
        {documents.isError ? (
          <div className="p-6">
            <ErrorState
              title="We couldn't load your documents"
              description="The documents service didn't respond. Your files are safe."
              onRetry={() => void documents.refetch()}
            />
          </div>
        ) : (
          <DocumentTable
            documents={visibleDocuments}
            isPending={documents.isPending}
            onDelete={setPendingDelete}
            onArchive={handleArchive}
            emptyState={
              <div className="p-6">
                <EmptyState
                  icon={FileText}
                  title={filters.search || filters.status !== "all" ? "No matching documents" : "No documents yet"}
                  description={
                    filters.search || filters.status !== "all"
                      ? "Try adjusting your search or clearing the active filters."
                      : "Upload your organization's first document to start building your knowledge base."
                  }
                  action={
                    filters.search || filters.status !== "all" ? (
                      <Button variant="outline" onClick={() => setFilters({ ...emptyFilterState })}>
                        Clear filters
                      </Button>
                    ) : (
                      <Button onClick={() => setUploadOpen(true)}>
                        <Upload className="mr-2 h-4 w-4" />
                        Upload document
                      </Button>
                    )
                  }
                />
              </div>
            }
          />
        )}
      </div>

      <p className="text-xs text-muted-foreground">{DEMO_NOTICE}</p>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={() => void documents.refetch()}
      />
      <CreateCollectionDialog open={collectionDialogOpen} onOpenChange={setCollectionDialogOpen} />

      <AlertDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this document?</AlertDialogTitle>
            <AlertDialogDescription>
              “{pendingDelete?.name}” will be permanently removed along with its indexed chunks.
              Answers that cite this document will no longer reference it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                handleDelete();
              }}
              className="bg-destructive text-white hover:bg-destructive/90"
            >
              Delete document
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
