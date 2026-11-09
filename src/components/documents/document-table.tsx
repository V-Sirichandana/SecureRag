"use client";

import Link from "next/link";
import { MoreHorizontal, Trash2, Download, FolderInput, Archive } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DocumentStatusBadge, ClassificationBadge } from "@/components/common/status-badge";
import { formatBytes, timeAgo } from "@/lib/utils";
import type { DocumentRecord } from "@/lib/types";

const fileTypeTone: Record<string, string> = {
  pdf: "bg-destructive/10 text-destructive",
  docx: "bg-primary/10 text-primary",
  xlsx: "bg-success/10 text-success",
  csv: "bg-warning/10 text-warning",
  pptx: "bg-warning/10 text-warning",
  txt: "bg-muted text-muted-foreground",
  md: "bg-chart-3/10 text-chart-3",
};

function FileGlyph({ type, name }: { type: string; name: string }) {
  return (
    <span
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-[10px] font-bold uppercase ${fileTypeTone[type] ?? "bg-muted text-muted-foreground"}`}
      aria-hidden="true"
    >
      {type || name.slice(-3)}
    </span>
  );
}

interface DocumentTableProps {
  documents: DocumentRecord[];
  onDelete: (document: DocumentRecord) => void;
  onArchive: (document: DocumentRecord) => void;
  emptyState?: React.ReactNode;
  isPending?: boolean;
}

export function DocumentTable({
  documents,
  onDelete,
  onArchive,
  emptyState,
  isPending,
}: DocumentTableProps) {
  if (isPending) {
    return (
      <div className="space-y-3 p-4">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="flex animate-pulse items-center gap-4">
            <span className="h-9 w-9 rounded-md bg-muted" />
            <span className="h-4 flex-1 rounded bg-muted" />
            <span className="h-4 w-24 rounded bg-muted" />
            <span className="h-4 w-20 rounded bg-muted" />
          </div>
        ))}
      </div>
    );
  }

  if (documents.length === 0) return <>{emptyState}</>;

  return (
    <>
      {/* Desktop / tablet table */}
      <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="min-w-[260px]">Document</TableHead>
              <TableHead>Collection</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead className="text-right">Size</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead className="w-12 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.map((document) => (
              <TableRow key={document.id}>
                <TableCell>
                  <Link
                    href={`/app/documents/${document.id}`}
                    className="flex items-center gap-3 group"
                  >
                    <FileGlyph type={document.fileType} name={document.name} />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium group-hover:text-primary">
                        {document.name}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {document.department} · {document.pageCount} pages
                      </span>
                    </span>
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary" className="font-normal">
                    {document.collectionName}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{document.owner}</TableCell>
                <TableCell className="text-right text-sm tabular-nums text-muted-foreground">
                  {formatBytes(document.sizeBytes)}
                </TableCell>
                <TableCell>
                  <div className="flex flex-col gap-1">
                    <DocumentStatusBadge status={document.status} />
                    <ClassificationBadge value={document.classification} />
                  </div>
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                  {timeAgo(document.updatedAt)}
                </TableCell>
                <TableCell className="text-right">
                  <RowActions
                    document={document}
                    onDelete={onDelete}
                    onArchive={onArchive}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Mobile cards */}
      <div className="divide-y md:hidden">
        {documents.map((document) => (
          <div key={document.id} className="flex items-start gap-3 p-4">
            <FileGlyph type={document.fileType} name={document.name} />
            <Link href={`/app/documents/${document.id}`} className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{document.name}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {document.collectionName} · {formatBytes(document.sizeBytes)} ·{" "}
                {timeAgo(document.updatedAt)}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <DocumentStatusBadge status={document.status} />
                <ClassificationBadge value={document.classification} />
              </div>
            </Link>
            <RowActions document={document} onDelete={onDelete} onArchive={onArchive} />
          </div>
        ))}
      </div>
    </>
  );
}

function RowActions({
  document,
  onDelete,
  onArchive,
}: {
  document: DocumentRecord;
  onDelete: (document: DocumentRecord) => void;
  onArchive: (document: DocumentRecord) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground"
          aria-label={`Actions for ${document.name}`}
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem asChild>
          <Link href={`/app/documents/${document.id}`}>
            <FolderInput className="mr-2 h-4 w-4" />
            Open details
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem>
          <Download className="mr-2 h-4 w-4" />
          Download
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => onArchive(document)}>
          <Archive className="mr-2 h-4 w-4" />
          Archive
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-destructive focus:text-destructive"
          onClick={() => onDelete(document)}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

