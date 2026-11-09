import type { DocumentRecord, DocumentStatus } from "@/lib/types";

export const UPLOAD_ACCEPTED_EXTENSIONS = ["pdf", "docx", "txt", "csv", "md"] as const;
export const acceptedFileTypes = UPLOAD_ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(",");
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isValidUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

export function isSupportedFile(name: string): boolean {
  const extension = name.split(".").pop()?.toLowerCase() ?? "";
  return UPLOAD_ACCEPTED_EXTENSIONS.includes(
    extension as (typeof UPLOAD_ACCEPTED_EXTENSIONS)[number],
  );
}

export function isWithinUploadSizeLimit(size: number): boolean {
  return Number.isFinite(size) && size > 0 && size <= MAX_UPLOAD_BYTES;
}

export type CollectionLoadState = "loading" | "error" | "ready";

export type UploadReadinessCode =
  | "loading"
  | "load-failed"
  | "empty"
  | "missing"
  | "invalid"
  | "uploading"
  | "no-files"
  | "ready";

export interface UploadReadiness {
  ready: boolean;
  code: UploadReadinessCode;
  message: string | null;
}

export function getCollectionReadiness(input: {
  state: CollectionLoadState;
  collectionCount: number;
  collectionId: string | null | undefined;
}): UploadReadiness {
  if (input.state === "loading") {
    return { ready: false, code: "loading", message: "Loading collections…" };
  }
  if (input.state === "error") {
    return {
      ready: false,
      code: "load-failed",
      message: "Collections could not be loaded. Retry before uploading.",
    };
  }
  if (input.collectionCount === 0) {
    return {
      ready: false,
      code: "empty",
      message: "No collections are available. Create a collection before uploading.",
    };
  }
  if (!input.collectionId) {
    return {
      ready: false,
      code: "missing",
      message: "Select a collection to upload.",
    };
  }
  if (!isValidUuid(input.collectionId)) {
    return {
      ready: false,
      code: "invalid",
      message: "The selected collection ID is invalid. Choose another collection.",
    };
  }
  return { ready: true, code: "ready", message: null };
}

export function getUploadReadiness(input: {
  collectionsState: CollectionLoadState;
  collectionCount: number;
  collectionId: string | null | undefined;
  fileCount: number;
  isUploading: boolean;
}): UploadReadiness {
  const collection = getCollectionReadiness({
    state: input.collectionsState,
    collectionCount: input.collectionCount,
    collectionId: input.collectionId,
  });
  if (!collection.ready) return collection;

  if (input.isUploading) {
    return {
      ready: false,
      code: "uploading",
      message: "An upload is already in progress.",
    };
  }
  if (input.fileCount === 0) {
    return {
      ready: false,
      code: "no-files",
      message: "Select at least one file to upload.",
    };
  }
  return { ready: true, code: "ready", message: null };
}

export type UploadOutcomeKind = "success" | "processing" | "failed";

export interface UploadOutcome {
  kind: UploadOutcomeKind;
  status: DocumentStatus | null;
  message: string;
}

export function getUploadOutcome(
  document: Pick<DocumentRecord, "id" | "status"> | null | undefined,
): UploadOutcome {
  if (!document?.id) {
    return {
      kind: "failed",
      status: null,
      message: "The server returned an invalid upload response.",
    };
  }

  switch (document.status) {
    case "ready":
      return {
        kind: "success",
        status: document.status,
        message: "Stored, indexed and ready to search.",
      };
    case "processing":
      return {
        kind: "processing",
        status: document.status,
        message: "Upload accepted, but indexing is still in progress. The document is not searchable yet.",
      };
    case "failed":
      return {
        kind: "failed",
        status: document.status,
        message: "Indexing failed on the server. The document is not searchable.",
      };
    case "archived":
      return {
        kind: "failed",
        status: document.status,
        message: "The server returned an archived status for a new upload.",
      };
  }
}

export function getUploadErrorMessage(error: unknown): string {
  const message =
    error instanceof Error ? error.message : typeof error === "string" ? error : "";
  const trimmed = message.trim();
  return trimmed || "Upload failed. Please check your connection and try again.";
}
