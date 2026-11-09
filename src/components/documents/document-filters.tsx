"use client";

import { Search, SlidersHorizontal, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { departments } from "@/lib/mock/users";
import type { Classification, DocumentStatus, FileType } from "@/lib/types";

export interface DocumentFilterState {
  search: string;
  collectionId: string;
  department: string;
  classification: Classification | "all";
  fileType: FileType | "all";
  status: DocumentStatus | "all";
  uploaded: string;
}

export const emptyFilterState: DocumentFilterState = {
  search: "",
  collectionId: "all",
  department: "all",
  classification: "all",
  fileType: "all",
  status: "all",
  uploaded: "any",
};

const allOption = "all";

function FilterSelect({
  label,
  value,
  onValueChange,
  options,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="space-y-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger className="h-9 w-full bg-background" aria-label={label}>
          <SelectValue placeholder={label} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

interface DocumentFiltersProps {
  value: DocumentFilterState;
  onChange: (next: DocumentFilterState) => void;
  collections: { id: string; name: string }[];
}

export function DocumentFilters({ value, onChange, collections }: DocumentFiltersProps) {
  const set = (patch: Partial<DocumentFilterState>) => onChange({ ...value, ...patch });

  const activeCount = [
    value.collectionId !== allOption,
    value.department !== allOption,
    value.classification !== allOption,
    value.fileType !== allOption,
    value.status !== allOption,
    value.uploaded !== "any",
  ].filter(Boolean).length;

  return (
    <div className="space-y-4 rounded-xl border bg-card p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={value.search}
            onChange={(event) => set({ search: event.target.value })}
            placeholder="Search by document name or owner…"
            className="pl-9"
            aria-label="Search documents"
          />
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant="secondary"
            className="hidden gap-1.5 sm:inline-flex"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            {activeCount} filter{activeCount === 1 ? "" : "s"} active
          </Badge>
          {activeCount > 0 || value.search ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onChange({ ...emptyFilterState })}
              className="text-muted-foreground"
            >
              <X className="mr-1.5 h-4 w-4" />
              Clear
            </Button>
          ) : null}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <FilterSelect
          label="Collection"
          value={value.collectionId}
          onValueChange={(next) => set({ collectionId: next })}
          options={[
            { value: allOption, label: "All collections" },
            ...collections.map((collection) => ({ value: collection.id, label: collection.name })),
          ]}
        />
        <FilterSelect
          label="Department"
          value={value.department}
          onValueChange={(next) => set({ department: next })}
          options={[
            { value: allOption, label: "All departments" },
            ...departments.map((department) => ({ value: department, label: department })),
          ]}
        />
        <FilterSelect
          label="Classification"
          value={value.classification}
          onValueChange={(next) => set({ classification: next as Classification | "all" })}
          options={[
            { value: allOption, label: "Any classification" },
            { value: "public", label: "Public" },
            { value: "internal", label: "Internal" },
            { value: "confidential", label: "Confidential" },
            { value: "restricted", label: "Restricted" },
          ]}
        />
        <FilterSelect
          label="File type"
          value={value.fileType}
          onValueChange={(next) => set({ fileType: next as FileType | "all" })}
          options={[
            { value: allOption, label: "All file types" },
            { value: "pdf", label: "PDF" },
            { value: "docx", label: "DOCX" },
            { value: "txt", label: "TXT" },
            { value: "csv", label: "CSV" },
            { value: "xlsx", label: "XLSX" },
            { value: "pptx", label: "PPTX" },
            { value: "md", label: "Markdown" },
          ]}
        />
        <FilterSelect
          label="Upload date"
          value={value.uploaded}
          onValueChange={(next) => set({ uploaded: next })}
          options={[
            { value: "any", label: "Any time" },
            { value: "24h", label: "Last 24 hours" },
            { value: "7d", label: "Last 7 days" },
            { value: "30d", label: "Last 30 days" },
          ]}
        />
        <FilterSelect
          label="Status"
          value={value.status}
          onValueChange={(next) => set({ status: next as DocumentStatus | "all" })}
          options={[
            { value: allOption, label: "Any status" },
            { value: "processing", label: "Processing" },
            { value: "ready", label: "Ready" },
            { value: "failed", label: "Failed" },
            { value: "archived", label: "Archived" },
          ]}
        />
      </div>
    </div>
  );
}
