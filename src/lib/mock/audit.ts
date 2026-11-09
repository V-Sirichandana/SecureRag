import type { AuditAction, AuditEvent } from "@/lib/types";
import { iso } from "./utils";

export const auditActions: AuditAction[] = [
  "LOGIN",
  "LOGOUT",
  "DOCUMENT_UPLOAD",
  "DOCUMENT_VIEW",
  "DOCUMENT_DELETE",
  "QUERY",
  "USER_INVITED",
  "PERMISSION_CHANGED",
  "API_KEY_CREATED",
];

function event(
  id: string,
  minutesAgo: number,
  user: string,
  email: string,
  action: AuditAction,
  resource: string,
  resourceType: string,
  ip: string,
  status: "success" | "failure",
): AuditEvent {
  return {
    id,
    timestamp: iso({ minutes: minutesAgo }),
    user,
    userEmail: email,
    action,
    resource,
    resourceType,
    ipAddress: ip,
    status,
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/141.0 Safari/537.36",
    metadata: {
      organization: "Acme Technologies",
      session: `sess_${id.slice(-6)}`,
      region: "eu-west-1",
    },
  };
}

export const auditLogs: AuditEvent[] = [
  event("aud_01", 6, "Sarah Johnson", "sarah@acmetech.io", "DOCUMENT_VIEW", "Employee Handbook.pdf", "document", "192.168.4.21", "success"),
  event("aud_02", 14, "Vishvendra Vadla", "vishvendra@acmetech.io", "DOCUMENT_UPLOAD", "Board Deck Q3.pptx", "document", "10.0.12.4", "success"),
  event("aud_03", 32, "Alex Morgan", "alex@acmetech.io", "QUERY", "Engineering collection", "collection", "10.0.12.88", "success"),
  event("aud_04", 48, "Tom Bradley", "tom@acmetech.io", "LOGIN", "Web application", "session", "203.0.113.44", "failure"),
  event("aud_05", 61, "Sarah Johnson", "sarah@acmetech.io", "USER_INVITED", "elena@acmetech.io", "user", "192.168.4.21", "success"),
  event("aud_06", 88, "Alex Morgan", "alex@acmetech.io", "API_KEY_CREATED", "Production", "api_key", "10.0.12.88", "success"),
  event("aud_07", 120, "Daniel Smith", "daniel@acmetech.io", "DOCUMENT_VIEW", "Financial Report.pdf", "document", "10.0.19.7", "success"),
  event("aud_08", 154, "Vishvendra Vadla", "vishvendra@acmetech.io", "PERMISSION_CHANGED", "Security Policy.pdf", "document", "10.0.12.4", "success"),
  event("aud_09", 190, "Priya Nair", "priya@acmetech.io", "QUERY", "HR collection", "collection", "10.0.12.91", "success"),
  event("aud_10", 240, "Marcus Webb", "marcus@acmetech.io", "DOCUMENT_DELETE", "Draft Roadmap.docx", "document", "198.51.100.20", "failure"),
  event("aud_11", 300, "Sarah Johnson", "sarah@acmetech.io", "LOGOUT", "Web application", "session", "192.168.4.21", "success"),
  event("aud_12", 360, "Daniel Smith", "daniel@acmetech.io", "QUERY", "Finance collection", "collection", "10.0.19.7", "success"),
  event("aud_13", 430, "Alex Morgan", "alex@acmetech.io", "DOCUMENT_UPLOAD", "Engineering Architecture.pdf", "document", "10.0.12.88", "success"),
  event("aud_14", 520, "Vishvendra Vadla", "vishvendra@acmetech.io", "LOGIN", "Web application", "session", "10.0.12.4", "success"),
  event("aud_15", 610, "Tom Bradley", "tom@acmetech.io", "QUERY", "Finance collection", "collection", "203.0.113.44", "failure"),
  event("aud_16", 700, "Priya Nair", "priya@acmetech.io", "PERMISSION_CHANGED", "Engineering collection", "collection", "10.0.12.91", "success"),
  event("aud_17", 780, "Sarah Johnson", "sarah@acmetech.io", "DOCUMENT_VIEW", "HR Policy.pdf", "document", "192.168.4.21", "success"),
  event("aud_18", 900, "Marcus Webb", "marcus@acmetech.io", "LOGIN", "Web application", "session", "198.51.100.20", "success"),
  event("aud_19", 1020, "Alex Morgan", "alex@acmetech.io", "API_KEY_CREATED", "Development", "api_key", "10.0.12.88", "success"),
  event("aud_20", 1140, "Daniel Smith", "daniel@acmetech.io", "LOGOUT", "Web application", "session", "10.0.19.7", "success"),
];
