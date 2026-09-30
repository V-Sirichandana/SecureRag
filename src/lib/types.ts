export type ID = string;

export type Role = "owner" | "admin" | "manager" | "member" | "viewer";

export type DocumentStatus = "processing" | "ready" | "failed" | "archived";

export type Classification = "public" | "internal" | "confidential" | "restricted";

export type FileType = "pdf" | "docx" | "txt" | "csv" | "xlsx" | "pptx" | "md";

export type UserStatus = "active" | "invited" | "disabled";

export type AuditStatus = "success" | "failure";

export type AuditAction =
  | "LOGIN"
  | "LOGOUT"
  | "DOCUMENT_UPLOAD"
  | "DOCUMENT_VIEW"
  | "DOCUMENT_DELETE"
  | "QUERY"
  | "USER_INVITED"
  | "PERMISSION_CHANGED"
  | "API_KEY_CREATED";

export type TimeRange = "7d" | "30d" | "90d";

export interface Organization {
  id: ID;
  name: string;
  plan: "Enterprise" | "Business" | "Free";
  memberCount: number;
  role: Role;
  createdAt: string;
}

export interface CurrentUser {
  id: ID;
  name: string;
  email: string;
  role: Role;
  department: string;
  avatarUrl?: string;
}

export interface User {
  id: ID;
  name: string;
  email: string;
  role: Role;
  department: string;
  status: UserStatus;
  lastActive: string;
  createdAt: string;
}

export interface Collection {
  id: ID;
  name: string;
  description: string;
  documentCount: number;
  owner: string;
  updatedAt: string;
  visibility: "everyone" | "members" | "restricted";
  color: string;
}

export interface DocumentRecord {
  id: ID;
  name: string;
  fileType: FileType;
  sizeBytes: number;
  collectionId: ID;
  collectionName: string;
  owner: string;
  department: string;
  classification: Classification;
  status: DocumentStatus;
  createdAt: string;
  updatedAt: string;
  pageCount: number;
  chunkCount: number;
  tags: string[];
}

export interface DocumentPage {
  pageNumber: number;
  title: string;
  paragraphs: { id: string; text: string; highlight?: string }[];
}

export interface Citation {
  index: number;
  documentId: ID;
  documentName: string;
  collectionName: string;
  pageNumber: number;
  quote: string;
}

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: ID;
  role: MessageRole;
  content: string;
  citations?: Citation[];
  createdAt: string;
  model?: string;
  latencyMs?: number;
  tokenCount?: number;
  feedback?: "up" | "down" | null;
}

export interface Conversation {
  id: ID;
  title: string;
  collectionId: ID | null;
  updatedAt: string;
  messageCount: number;
  messages: ChatMessage[];
}

export interface AuditEvent {
  id: ID;
  timestamp: string;
  user: string;
  userEmail: string;
  action: AuditAction;
  resource: string;
  resourceType: string;
  ipAddress: string;
  status: AuditStatus;
  userAgent: string;
  metadata: Record<string, string>;
}

export interface ApiKey {
  id: ID;
  name: string;
  environment: "live" | "test";
  maskedKey: string;
  createdAt: string;
  lastUsedAt: string | null;
  expiresAt: string | null;
  permissions: string[];
}

export interface MetricPoint {
  date: string;
  queries: number;
  successful: number;
  failed: number;
  tokens: number;
  latencyMs: number;
  storageGb: number;
}

export interface UsageMetrics {
  totalQueries: number;
  tokensConsumed: number;
  averageLatencyMs: number;
  documentsProcessed: number;
  storageUsedGb: number;
  storageQuotaGb: number;
  apiRequests: number;
  series: MetricPoint[];
  modelUsage: { model: string; requests: number; share: number }[];
}

export interface DashboardStats {
  documents: { value: number; delta: number; label: string };
  users: { value: number; delta: number; label: string };
  queries: { value: number; delta: number; label: string };
  storage: { value: number; quota: number; label: string };
}

export interface RetrievalPerformance {
  avgResponseMs: number;
  retrievalAccuracy: number;
  citationCoverage: number;
  failedQueries: number;
}

export interface ActivityEvent {
  id: ID;
  actor: string;
  action: string;
  target: string;
  timestamp: string;
  type: "upload" | "invite" | "api_key" | "update" | "query" | "permission";
}

export interface SecurityStatusItem {
  label: string;
  status: "active" | "attention" | "inactive";
  detail: string;
  demo: boolean;
}

export type PermissionKey =
  | "view_documents"
  | "upload_documents"
  | "delete_documents"
  | "manage_users"
  | "manage_roles"
  | "view_audit_logs"
  | "manage_api_keys"
  | "manage_ai_settings";

export type PermissionMatrix = Record<PermissionKey, Record<Role, boolean>>;

export interface SettingsGeneral {
  organizationName: string;
  description: string;
  defaultCollectionId: ID;
  supportEmail: string;
}

export interface SettingsSecurity {
  mfaRequired: boolean;
  sessionTimeoutMinutes: number;
  minPasswordLength: number;
  requireUppercase: boolean;
  requireNumber: boolean;
  ssoEnabled: boolean;
  ssoProvider: string;
  ipAllowlistEnabled: boolean;
  ipAllowlist: string[];
}

export interface SettingsAI {
  defaultModel: string;
  temperature: number;
  maxResponseTokens: number;
  retrievalTopK: number;
  rerankingEnabled: boolean;
  requireCitations: boolean;
}

export interface SettingsNotifications {
  securityAlerts: boolean;
  memberJoinedAlerts: boolean;
  documentProcessingAlerts: boolean;
  usageThresholdAlerts: boolean;
  weeklyDigest: boolean;
  productUpdates: boolean;
}

export interface SettingsBilling {
  planName: string;
  planPrice: string;
  seatsUsed: number;
  seatsTotal: number;
  storageUsedGb: number;
  storageTotalGb: number;
  renewsAt: string;
  billingEmail: string;
  autoRenew: boolean;
  invoiceDelivery: "email" | "portal";
  purchaseOrderNumber: string;
}

export interface Invoice {
  id: ID;
  number: string;
  issuedAt: string;
  amount: string;
  status: "paid" | "open" | "refunded";
}

export interface SearchResult {
  id: ID;
  title: string;
  subtitle: string;
  type: "document" | "user" | "collection" | "setting" | "page";
  href: string;
}
