import { USE_MOCKS, request } from "./client";
import { documents as mockDocuments, documentPages, fallbackPages } from "@/lib/mock/documents";
import { latency } from "@/lib/mock/utils";
import type { Classification, DocumentRecord, DocumentStatus, FileType } from "@/lib/types";

export interface DocumentFilters {
  search?: string;
  collectionId?: string;
  department?: string;
  classification?: Classification | "all";
  fileType?: FileType | "all";
  status?: DocumentStatus | "all";
}

export async function getDocuments(filters: DocumentFilters = {}): Promise<DocumentRecord[]> {
  if (USE_MOCKS) {
    await latency();
    const search = filters.search?.trim().toLowerCase();
    return mockDocuments.filter((doc) => {
      if (search && !doc.name.toLowerCase().includes(search) && !doc.owner.toLowerCase().includes(search)) {
        return false;
      }
      if (filters.collectionId && filters.collectionId !== "all" && doc.collectionId !== filters.collectionId) {
        return false;
      }
      if (filters.department && filters.department !== "all" && doc.department !== filters.department) {
        return false;
      }
      if (filters.classification && filters.classification !== "all" && doc.classification !== filters.classification) {
        return false;
      }
      if (filters.fileType && filters.fileType !== "all" && doc.fileType !== filters.fileType) {
        return false;
      }
      if (filters.status && filters.status !== "all" && doc.status !== filters.status) {
        return false;
      }
      return true;
    });
  }
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value && value !== "all") params.set(key, String(value));
  });
  return request<DocumentRecord[]>(`/documents?${params.toString()}`);
}

export async function getDocument(id: string): Promise<DocumentRecord> {
  if (USE_MOCKS) {
    await latency(250, 550);
    const doc = mockDocuments.find((item) => item.id === id);
    if (!doc) throw new Error("Document not found");
    return doc;
  }
  return request<DocumentRecord>(`/documents/${id}`);
}

export async function getDocumentPages(id: string) {
  if (USE_MOCKS) {
    await latency(300, 600);
    const doc = mockDocuments.find((item) => item.id === id);
    if (!doc) throw new Error("Document not found");
    return documentPages[id] ?? fallbackPages(doc.name);
  }
  return request<Awaited<ReturnType<typeof fallbackPages>>>(`/documents/${id}/pages`);
}

export async function uploadDocument(input: {
  name: string;
  collectionId: string;
  classification: Classification;
}): Promise<DocumentRecord> {
  if (USE_MOCKS) {
    await latency(900, 1600);
    const collection = mockDocuments.find((doc) => doc.collectionId === input.collectionId);
    const extension = input.name.split(".").pop()?.toLowerCase() as FileType;
    const created: DocumentRecord = {
      id: `doc_${Math.random().toString(36).slice(2, 9)}`,
      name: input.name,
      fileType: extension,
      sizeBytes: Math.round(400_000 + Math.random() * 6_000_000),
      collectionId: input.collectionId,
      collectionName: collection?.collectionName ?? "Unfiled",
      owner: "Vishvendra Vadla",
      department: "Executive",
      classification: input.classification,
      status: "processing",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      pageCount: Math.round(4 + Math.random() * 60),
      chunkCount: 0,
      tags: [],
    };
    mockDocuments.unshift(created);
    return created;
  }
  return request<DocumentRecord>("/documents", { method: "POST", body: input });
}

export async function updateDocument(
  id: string,
  patch: Partial<Pick<DocumentRecord, "collectionId" | "classification" | "status" | "name">>,
): Promise<DocumentRecord> {
  if (USE_MOCKS) {
    await latency(300, 650);
    const doc = mockDocuments.find((item) => item.id === id);
    if (!doc) throw new Error("Document not found");
    Object.assign(doc, patch, { updatedAt: new Date().toISOString() });
    return { ...doc };
  }
  return request<DocumentRecord>(`/documents/${id}`, { method: "PATCH", body: patch });
}

export async function deleteDocument(id: string): Promise<void> {
  if (USE_MOCKS) {
    await latency(250, 500);
    const index = mockDocuments.findIndex((item) => item.id === id);
    if (index >= 0) mockDocuments.splice(index, 1);
    return;
  }
  await request(`/documents/${id}`, { method: "DELETE" });
}

export async function updateDocumentPermissions(
  id: string,
  scope: "everyone" | "members" | "roles" | "users",
  targets: string[],
): Promise<{ id: string; scope: string; targets: string[] }> {
  if (USE_MOCKS) {
    await latency(400, 800);
    return { id, scope, targets };
  }
  return request(`/documents/${id}/permissions`, { method: "PUT", body: { scope, targets } });
}
