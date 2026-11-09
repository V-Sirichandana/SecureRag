"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  getAuditLogs,
  getActivitySeries,
  getApiKeys,
  getDashboardStats,
  getUsage,
  createApiKey,
  revokeApiKey,
  type AuditFilters,
  type UsageWindow,
} from "@/lib/api/analytics";
import {
  createCollection,
  getCollections,
  getUsers,
  inviteUser,
  removeUser,
  updateUserRole,
  updateUserStatus,
} from "@/lib/api/directory";
import {
  deleteDocument,
  getDocument,
  getDocumentPages,
  getDocuments,
  updateDocument,
  updateDocumentPermissions,
  uploadDocument,
  type DocumentFilters,
} from "@/lib/api/documents";
import {
  createConversation,
  deleteConversation,
  getConversation,
  getConversations,
} from "@/lib/api/chat";
import {
  getAISettings,
  getBillingSettings,
  getGeneralSettings,
  getInvoices,
  getNotificationSettings,
  getSecuritySettings,
  saveAISettings,
  saveBillingSettings,
  saveGeneralSettings,
  saveNotificationSettings,
  saveSecuritySettings,
} from "@/lib/api/settings";
import type { TimeRange } from "@/lib/types";

export const queryKeys = {
  documents: (filters: DocumentFilters) => ["documents", filters] as const,
  document: (id: string) => ["document", id] as const,
  documentPages: (id: string) => ["document-pages", id] as const,
  collections: ["collections"] as const,
  users: ["users"] as const,
  conversations: ["conversations"] as const,
  conversation: (id: string) => ["conversation", id] as const,
  dashboard: ["dashboard"] as const,
  usage: (range: TimeRange, custom?: UsageWindow) =>
    ["usage", range, custom?.from ?? null, custom?.to ?? null] as const,
  activity: (range: TimeRange) => ["activity", range] as const,
  audit: (filters: AuditFilters) => ["audit", filters] as const,
  apiKeys: ["api-keys"] as const,
  settings: {
    general: ["settings", "general"] as const,
    security: ["settings", "security"] as const,
    ai: ["settings", "ai"] as const,
    notifications: ["settings", "notifications"] as const,
    billing: ["settings", "billing"] as const,
  },
  invoices: ["invoices"] as const,
};

/* ---------------------------------- reads --------------------------------- */

export function useDocuments(filters: DocumentFilters = {}) {
  return useQuery({
    queryKey: queryKeys.documents(filters),
    queryFn: () => getDocuments(filters),
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: queryKeys.document(id),
    queryFn: () => getDocument(id),
    enabled: Boolean(id),
  });
}

export function useDocumentPages(id: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.documentPages(id),
    queryFn: () => getDocumentPages(id),
    enabled: Boolean(id) && enabled,
  });
}

export function useCollections() {
  return useQuery({ queryKey: queryKeys.collections, queryFn: getCollections });
}

export function useUsers() {
  return useQuery({ queryKey: queryKeys.users, queryFn: getUsers });
}

export function useConversations() {
  return useQuery({ queryKey: queryKeys.conversations, queryFn: getConversations });
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: queryKeys.conversation(id),
    queryFn: () => getConversation(id),
    enabled: Boolean(id),
  });
}

export function useDashboard() {
  return useQuery({ queryKey: queryKeys.dashboard, queryFn: getDashboardStats });
}

export function useUsage(range: TimeRange, custom?: UsageWindow) {
  return useQuery({
    queryKey: queryKeys.usage(range, custom),
    queryFn: () => getUsage(range, custom),
  });
}

export function useActivitySeries(range: TimeRange) {
  return useQuery({
    queryKey: queryKeys.activity(range),
    queryFn: () => getActivitySeries(range),
  });
}

export function useAuditLogs(filters: AuditFilters) {
  return useQuery({
    queryKey: queryKeys.audit(filters),
    queryFn: () => getAuditLogs(filters),
  });
}

export function useApiKeys() {
  return useQuery({ queryKey: queryKeys.apiKeys, queryFn: getApiKeys });
}

export function useGeneralSettings() {
  return useQuery({ queryKey: queryKeys.settings.general, queryFn: getGeneralSettings });
}

export function useSecuritySettings() {
  return useQuery({ queryKey: queryKeys.settings.security, queryFn: getSecuritySettings });
}

export function useAISettings() {
  return useQuery({ queryKey: queryKeys.settings.ai, queryFn: getAISettings });
}

export function useNotificationSettings() {
  return useQuery({
    queryKey: queryKeys.settings.notifications,
    queryFn: getNotificationSettings,
  });
}

export function useBillingSettings() {
  return useQuery({ queryKey: queryKeys.settings.billing, queryFn: getBillingSettings });
}

export function useInvoices() {
  return useQuery({ queryKey: queryKeys.invoices, queryFn: getInvoices });
}

/* -------------------------------- mutations ------------------------------- */

type MutationOptions<TData, TVars> = {
  onSuccess?: (data: TData, variables: TVars) => void;
  onError?: (error: Error) => void;
};

export function useUploadDocument(options?: MutationOptions<Awaited<ReturnType<typeof uploadDocument>>, Parameters<typeof uploadDocument>[0]>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: uploadDocument,
    ...options,
    onSuccess: (data, vars) => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      options?.onSuccess?.(data, vars);
    },
  });
}

export function useDeleteDocument(options?: MutationOptions<void, string>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDocument,
    ...options,
    onSuccess: (data, vars) => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      options?.onSuccess?.(data, vars);
    },
  });
}

export function useUpdateDocument(
  options?: MutationOptions<
    Awaited<ReturnType<typeof updateDocument>>,
    Parameters<typeof updateDocument>
  >,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ([id, patch]: [string, Parameters<typeof updateDocument>[1]]) =>
      updateDocument(id, patch),
    ...options,
    onSuccess: (data, vars) => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.document(vars[0]) });
      options?.onSuccess?.(data, vars);
    },
  });
}

export function useUpdateDocumentPermissions() {
  return useMutation({
    mutationFn: ({
      id,
      scope,
      targets,
    }: {
      id: string;
      scope: "everyone" | "members" | "roles" | "users";
      targets: string[];
    }) => updateDocumentPermissions(id, scope, targets),
    onSuccess: () => toast.success("Document permissions updated."),
    onError: (error) => toast.error(error.message || "Permission update failed."),
  });
}

export function useCreateCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCollection,
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections });
      toast.success(`Collection “${data.name}” created.`);
    },
    onError: (error) => toast.error(error.message || "Failed to create collection."),
  });
}

export function useInviteUser(options?: MutationOptions<Awaited<ReturnType<typeof inviteUser>>, Parameters<typeof inviteUser>[0]>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: inviteUser,
    ...options,
    onSuccess: (data, vars) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users });
      options?.onSuccess?.(data, vars);
    },
  });
}

export function useUpdateUserRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, role }: { id: string; role: Parameters<typeof updateUserRole>[1] }) =>
      updateUserRole(id, role),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users });
      toast.success("Role updated.");
    },
    onError: (error) => toast.error(error.message || "Failed to update role."),
  });
}

export function useUpdateUserStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: Parameters<typeof updateUserStatus>[1] }) =>
      updateUserStatus(id, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users });
      toast.success("User status updated.");
    },
    onError: (error) => toast.error(error.message || "Failed to update user."),
  });
}

export function useRemoveUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: removeUser,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users });
      toast.success("User removed.");
    },
    onError: (error) => toast.error(error.message || "Failed to remove user."),
  });
}

export function useCreateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createApiKey,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys });
    },
  });
}

export function useRevokeApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys });
      toast.success("API key revoked.");
    },
    onError: (error) => toast.error(error.message || "Failed to revoke key."),
  });
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ title, collectionId }: { title: string; collectionId: string | null }) =>
      createConversation(title, collectionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations });
    },
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations });
      toast.success("Conversation cleared.");
    },
  });
}

export function useSaveGeneralSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveGeneralSettings,
    onSuccess: (data) => {
      void queryClient.setQueryData(queryKeys.settings.general, data);
      toast.success("Organization settings saved.");
    },
    onError: (error) => toast.error(error.message || "Failed to save settings."),
  });
}

export function useSaveSecuritySettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveSecuritySettings,
    onSuccess: (data) => {
      void queryClient.setQueryData(queryKeys.settings.security, data);
      toast.success("Security settings saved.");
    },
    onError: (error) => toast.error(error.message || "Failed to save settings."),
  });
}

export function useSaveAISettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveAISettings,
    onSuccess: (data) => {
      void queryClient.setQueryData(queryKeys.settings.ai, data);
      toast.success("AI configuration saved.");
    },
    onError: (error) => toast.error(error.message || "Failed to save settings."),
  });
}

export function useSaveNotificationSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveNotificationSettings,
    onSuccess: (data) => {
      void queryClient.setQueryData(queryKeys.settings.notifications, data);
      toast.success("Notification settings saved.");
    },
    onError: (error) => toast.error(error.message || "Failed to save settings."),
  });
}

export function useSaveBillingSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveBillingSettings,
    onSuccess: (data) => {
      void queryClient.setQueryData(queryKeys.settings.billing, data);
      toast.success("Billing settings saved.");
    },
    onError: (error) => toast.error(error.message || "Failed to save settings."),
  });
}
