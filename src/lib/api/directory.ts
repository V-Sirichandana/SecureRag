import { USE_MOCKS, request } from "./client";
import { collections as mockCollections } from "@/lib/mock/documents";
import { users as mockUsers } from "@/lib/mock/users";
import { latency } from "@/lib/mock/utils";
import type { Collection, Role, User, UserStatus } from "@/lib/types";

export async function getCollections(): Promise<Collection[]> {
  if (USE_MOCKS) {
    await latency();
    return [...mockCollections];
  }
  return request<Collection[]>("/collections");
}

export async function createCollection(input: {
  name: string;
  description: string;
  visibility: Collection["visibility"];
}): Promise<Collection> {
  if (USE_MOCKS) {
    await latency(500, 900);
    const created: Collection = {
      id: `col_${Math.random().toString(36).slice(2, 8)}`,
      name: input.name,
      description: input.description,
      documentCount: 0,
      owner: "Vishvendra Vadla",
      updatedAt: new Date().toISOString(),
      visibility: input.visibility,
      color: "#6366f1",
    };
    mockCollections.unshift(created);
    return created;
  }
  return request<Collection>("/collections", { method: "POST", body: input });
}

export async function updateCollection(
  id: string,
  patch: Partial<Pick<Collection, "name" | "description" | "visibility">>,
): Promise<Collection> {
  if (USE_MOCKS) {
    await latency(350, 700);
    const found = mockCollections.find((item) => item.id === id);
    if (!found) throw new Error("Collection not found");
    Object.assign(found, patch, { updatedAt: new Date().toISOString() });
    return { ...found };
  }
  return request<Collection>(`/collections/${id}`, { method: "PATCH", body: patch });
}

export async function getUsers(): Promise<User[]> {
  if (USE_MOCKS) {
    await latency();
    return [...mockUsers];
  }
  return request<User[]>("/users");
}

export interface InviteUserPayload {
  email: string;
  role: Role;
  department: string;
  message?: string;
}

export async function inviteUser(payload: InviteUserPayload): Promise<User> {
  if (USE_MOCKS) {
    await latency(700, 1200);
    const created: User = {
      id: `usr_${Math.random().toString(36).slice(2, 8)}`,
      name: payload.email.split("@")[0].replace(/[._]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      email: payload.email,
      role: payload.role,
      department: payload.department,
      status: "invited",
      lastActive: new Date().toISOString(),
      createdAt: new Date().toISOString(),
    };
    mockUsers.unshift(created);
    return created;
  }
  return request<User>("/users/invite", { method: "POST", body: payload });
}

export async function updateUserRole(id: string, role: Role): Promise<User> {
  if (USE_MOCKS) {
    await latency(300, 600);
    const found = mockUsers.find((item) => item.id === id);
    if (!found) throw new Error("User not found");
    found.role = role;
    return { ...found };
  }
  return request<User>(`/users/${id}`, { method: "PATCH", body: { role } });
}

export async function updateUserStatus(id: string, status: UserStatus): Promise<User> {
  if (USE_MOCKS) {
    await latency(300, 600);
    const found = mockUsers.find((item) => item.id === id);
    if (!found) throw new Error("User not found");
    found.status = status;
    return { ...found };
  }
  return request<User>(`/users/${id}`, { method: "PATCH", body: { status } });
}

export async function removeUser(id: string): Promise<void> {
  if (USE_MOCKS) {
    await latency(300, 600);
    const index = mockUsers.findIndex((item) => item.id === id);
    if (index >= 0) mockUsers.splice(index, 1);
    return;
  }
  await request(`/users/${id}`, { method: "DELETE" });
}
