import { USE_MOCKS, request } from "./client";
import { documents, collections } from "@/lib/mock/documents";
import { users } from "@/lib/mock/users";
import { latency } from "@/lib/mock/utils";
import type { SearchResult } from "@/lib/types";

const settingRoutes: { title: string; href: string; keywords: string[] }[] = [
  { title: "General settings", href: "/app/settings/general", keywords: ["organization", "name", "logo", "description"] },
  { title: "Security settings", href: "/app/settings/security", keywords: ["mfa", "password", "sso", "session", "ip"] },
  { title: "AI configuration", href: "/app/settings/ai", keywords: ["model", "temperature", "retrieval", "citations"] },
  { title: "Roles & permissions", href: "/app/roles", keywords: ["permission", "matrix", "role"] },
  { title: "API keys", href: "/app/api-keys", keywords: ["token", "credential", "developer"] },
  { title: "Audit logs", href: "/app/audit-logs", keywords: ["security", "events", "activity"] },
  { title: "Usage analytics", href: "/app/usage", keywords: ["tokens", "queries", "latency", "storage"] },
  { title: "AI chat", href: "/app/chat", keywords: ["assistant", "ask", "question"] },
];

export async function globalSearch(query: string): Promise<SearchResult[]> {
  const q = query.trim().toLowerCase();
  if (!q) return [];

  if (USE_MOCKS) {
    await latency(120, 320);
    const results: SearchResult[] = [];

    documents
      .filter((doc) => doc.name.toLowerCase().includes(q))
      .slice(0, 5)
      .forEach((doc) =>
        results.push({
          id: doc.id,
          title: doc.name,
          subtitle: `${doc.collectionName} · ${doc.fileType.toUpperCase()}`,
          type: "document",
          href: `/app/documents/${doc.id}`,
        }),
      );

    collections
      .filter((col) => col.name.toLowerCase().includes(q))
      .slice(0, 4)
      .forEach((col) =>
        results.push({
          id: col.id,
          title: col.name,
          subtitle: `${col.documentCount} documents`,
          type: "collection",
          href: "/app/collections",
        }),
      );

    users
      .filter((user) => user.name.toLowerCase().includes(q) || user.email.toLowerCase().includes(q))
      .slice(0, 4)
      .forEach((user) =>
        results.push({
          id: user.id,
          title: user.name,
          subtitle: user.email,
          type: "user",
          href: "/app/users",
        }),
      );

    settingRoutes
      .filter(
        (route) =>
          route.title.toLowerCase().includes(q) ||
          route.keywords.some((keyword) => keyword.includes(q)),
      )
      .slice(0, 5)
      .forEach((route) =>
        results.push({
          id: route.href,
          title: route.title,
          subtitle: "Settings",
          type: "setting",
          href: route.href,
        }),
      );

    return results;
  }

  return request<SearchResult[]>(`/search?q=${encodeURIComponent(query)}`);
}
