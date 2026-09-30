import { USE_MOCKS, request } from "./client";
import { latency } from "@/lib/mock/utils";
import type { Organization } from "@/lib/types";

export interface LoginPayload {
  email: string;
  password: string;
  remember: boolean;
}

export interface AuthSession {
  user: {
    id: string;
    name: string;
    email: string;
    role: "owner" | "admin" | "manager" | "member" | "viewer";
    department: string;
    organizationId: string;
  };
  organizations: Organization[];
}

const organizations: Organization[] = [
  {
    id: "org_acme",
    name: "Acme Technologies",
    plan: "Enterprise",
    memberCount: 42,
    role: "owner",
    createdAt: "2025-06-01T00:00:00.000Z",
  },
  {
    id: "org_demo",
    name: "Demo Organization",
    plan: "Business",
    memberCount: 8,
    role: "admin",
    createdAt: "2025-11-14T00:00:00.000Z",
  },
];

function sessionFor(name: string, email: string): AuthSession {
  return {
    user: {
      id: "usr_vishv",
      name,
      email,
      role: "owner",
      department: "Executive",
      organizationId: "org_acme",
    },
    organizations,
  };
}

export async function login(payload: LoginPayload): Promise<AuthSession> {
  if (USE_MOCKS) {
    await latency(600, 1100);
    if (!payload.email.includes("@") || payload.password.length < 4) {
      throw new Error("Invalid email or password. Please try again.");
    }
    const name = payload.email.split("@")[0];
    const pretty = name
      .split(/[._-]/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
    return sessionFor(pretty || "Vishvendra Vadla", payload.email);
  }
  return request<AuthSession>("/auth/login", { method: "POST", body: payload });
}

export async function signup(payload: {
  name: string;
  email: string;
  password: string;
  organizationName: string;
}): Promise<AuthSession> {
  if (USE_MOCKS) {
    await latency(800, 1400);
    return sessionFor(payload.name, payload.email);
  }
  return request<AuthSession>("/auth/signup", { method: "POST", body: payload });
}

export async function requestPasswordReset(email: string): Promise<{ ok: true }> {
  if (USE_MOCKS) {
    await latency(600, 1000);
    return { ok: true };
  }
  return request("/auth/forgot-password", { method: "POST", body: { email } });
}

export async function logout(): Promise<void> {
  if (USE_MOCKS) {
    await latency(200, 400);
    return;
  }
  await request("/auth/logout", { method: "POST" });
}

export async function oauthSignIn(provider: "google" | "microsoft"): Promise<AuthSession> {
  if (USE_MOCKS) {
    await latency(700, 1200);
    return sessionFor("Vishvendra Vadla", `vishvendra@${provider === "google" ? "gmail" : "outlook"}.com`);
  }
  return request<AuthSession>(`/auth/oauth/${provider}`, { method: "POST" });
}
