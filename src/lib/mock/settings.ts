import type {
  ApiKey,
  Invoice,
  PermissionMatrix,
  SecurityStatusItem,
  SettingsAI,
  SettingsBilling,
  SettingsGeneral,
  SettingsNotifications,
  SettingsSecurity,
} from "@/lib/types";
import { daysFromNow, iso } from "./utils";

export const apiKeys: ApiKey[] = [
  {
    id: "key_prod",
    name: "Production",
    environment: "live",
    maskedKey: "sk_live_••••••••••••••••",
    createdAt: iso({ days: 30 }),
    lastUsedAt: iso({ minutes: 5 }),
    expiresAt: daysFromNow(335),
    permissions: ["documents:read", "chat:write", "collections:read"],
  },
  {
    id: "key_dev",
    name: "Development",
    environment: "test",
    maskedKey: "sk_test_••••••••••••••••",
    createdAt: iso({ days: 32 }),
    lastUsedAt: null,
    expiresAt: null,
    permissions: ["documents:read", "collections:read"],
  },
];

export const apiKeyPermissions = [
  { value: "documents:read", label: "Read documents" },
  { value: "documents:write", label: "Write documents" },
  { value: "collections:read", label: "Read collections" },
  { value: "chat:write", label: "Send chat queries" },
  { value: "usage:read", label: "Read usage metrics" },
];

export const defaultGeneral: SettingsGeneral = {
  organizationName: "Acme Technologies",
  description:
    "Multi-tenant knowledge platform used by Acme Technologies to ground AI answers in internal documentation.",
  defaultCollectionId: "col_hr",
  supportEmail: "platform@acmetech.io",
};

export const defaultSecurity: SettingsSecurity = {
  mfaRequired: true,
  sessionTimeoutMinutes: 60,
  minPasswordLength: 12,
  requireUppercase: true,
  requireNumber: true,
  ssoEnabled: false,
  ssoProvider: "Okta",
  ipAllowlistEnabled: false,
  ipAllowlist: ["10.0.0.0/8", "192.168.0.0/16"],
};

export const defaultAI: SettingsAI = {
  defaultModel: "gpt-4o-mini",
  temperature: 0.2,
  maxResponseTokens: 1024,
  retrievalTopK: 8,
  rerankingEnabled: true,
  requireCitations: true,
};

export const defaultNotifications: SettingsNotifications = {
  securityAlerts: true,
  memberJoinedAlerts: true,
  documentProcessingAlerts: true,
  usageThresholdAlerts: true,
  weeklyDigest: true,
  productUpdates: false,
};

export const defaultBilling: SettingsBilling = {
  planName: "Business",
  planPrice: "$24 / user / month",
  seatsUsed: 18,
  seatsTotal: 25,
  storageUsedGb: 42.6,
  storageTotalGb: 100,
  renewsAt: daysFromNow(21),
  billingEmail: "finance@acmetech.io",
  autoRenew: true,
  invoiceDelivery: "email",
  purchaseOrderNumber: "",
};

export const invoiceHistory: Invoice[] = [
  { id: "inv_0092", number: "INV-2026-0092", issuedAt: iso({ days: 9 }), amount: "$432.00", status: "paid" },
  { id: "inv_0081", number: "INV-2026-0081", issuedAt: iso({ days: 39 }), amount: "$432.00", status: "paid" },
  { id: "inv_0070", number: "INV-2026-0070", issuedAt: iso({ days: 69 }), amount: "$384.00", status: "paid" },
];

export const availableModels = [
  { value: "gpt-4o-mini", label: "GPT-4o mini", note: "Fast, cost-efficient" },
  { value: "gpt-4o", label: "GPT-4o", note: "Highest quality" },
  { value: "claude-3-5-sonnet", label: "Claude 3.5 Sonnet", note: "Strong reasoning" },
  { value: "llama-3.1-70b", label: "Llama 3.1 70B", note: "Self-hosted" },
];

export const permissionMatrix: PermissionMatrix = {
  view_documents: { owner: true, admin: true, manager: true, member: true, viewer: true },
  upload_documents: { owner: true, admin: true, manager: true, member: true, viewer: false },
  delete_documents: { owner: true, admin: true, manager: true, member: false, viewer: false },
  manage_users: { owner: true, admin: true, manager: false, member: false, viewer: false },
  manage_roles: { owner: true, admin: false, manager: false, member: false, viewer: false },
  view_audit_logs: { owner: true, admin: true, manager: true, member: false, viewer: false },
  manage_api_keys: { owner: true, admin: true, manager: false, member: false, viewer: false },
  manage_ai_settings: { owner: true, admin: true, manager: false, member: false, viewer: false },
};

export const permissionLabels: Record<keyof PermissionMatrix, string> = {
  view_documents: "View documents",
  upload_documents: "Upload documents",
  delete_documents: "Delete documents",
  manage_users: "Manage users",
  manage_roles: "Manage roles",
  view_audit_logs: "View audit logs",
  manage_api_keys: "Manage API keys",
  manage_ai_settings: "Manage AI settings",
};

export const securityOverview: SecurityStatusItem[] = [
  { label: "Tenant isolation", status: "active" as const, detail: "Per-organization index partitioning", demo: true },
  { label: "Role-based access", status: "active" as const, detail: "5 roles configured", demo: false },
  { label: "Audit logging", status: "active" as const, detail: "All actions retained 400 days", demo: false },
  { label: "Encryption", status: "active" as const, detail: "TLS in transit, AES-256 at rest", demo: true },
  { label: "API security", status: "active" as const, detail: "Scoped keys with expiry", demo: false },
];
