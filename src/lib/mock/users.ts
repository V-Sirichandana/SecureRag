import type { Role, User } from "@/lib/types";
import { iso } from "./utils";

export const users: User[] = [
  {
    id: "usr_vishv",
    name: "Vishvendra Vadla",
    email: "vishvendra@acmetech.io",
    role: "owner",
    department: "Executive",
    status: "active",
    lastActive: iso({ minutes: 2 }),
    createdAt: iso({ days: 400 }),
  },
  {
    id: "usr_sarah",
    name: "Sarah Johnson",
    email: "sarah@acmetech.io",
    role: "admin",
    department: "Human Resources",
    status: "active",
    lastActive: iso({ minutes: 12 }),
    createdAt: iso({ days: 365 }),
  },
  {
    id: "usr_alex",
    name: "Alex Morgan",
    email: "alex@acmetech.io",
    role: "member",
    department: "Engineering",
    status: "active",
    lastActive: iso({ hours: 1 }),
    createdAt: iso({ days: 300 }),
  },
  {
    id: "usr_daniel",
    name: "Daniel Smith",
    email: "daniel@acmetech.io",
    role: "manager",
    department: "Finance",
    status: "active",
    lastActive: iso({ hours: 5 }),
    createdAt: iso({ days: 240 }),
  },
  {
    id: "usr_priya",
    name: "Priya Nair",
    email: "priya@acmetech.io",
    role: "member",
    department: "Engineering",
    status: "active",
    lastActive: iso({ hours: 26 }),
    createdAt: iso({ days: 180 }),
  },
  {
    id: "usr_marcus",
    name: "Marcus Webb",
    email: "marcus@acmetech.io",
    role: "viewer",
    department: "Legal",
    status: "active",
    lastActive: iso({ days: 2 }),
    createdAt: iso({ days: 120 }),
  },
  {
    id: "usr_elena",
    name: "Elena Petrova",
    email: "elena@acmetech.io",
    role: "member",
    department: "Design",
    status: "invited",
    lastActive: iso({ days: 1 }),
    createdAt: iso({ days: 1 }),
  },
  {
    id: "usr_tom",
    name: "Tom Bradley",
    email: "tom@acmetech.io",
    role: "member",
    department: "Sales",
    status: "disabled",
    lastActive: iso({ days: 45 }),
    createdAt: iso({ days: 420 }),
  },
];

export const departments = [
  "Executive",
  "Human Resources",
  "Engineering",
  "Finance",
  "Legal",
  "Design",
  "Sales",
  "Security",
];

export const roleLabels: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  manager: "Manager",
  member: "Member",
  viewer: "Viewer",
};

export const roleDescriptions: Record<Role, string> = {
  owner: "Full control including billing, ownership transfer and destructive actions.",
  admin: "Manages users, roles, collections and organization settings.",
  manager: "Manages documents and team content within assigned collections.",
  member: "Uploads documents and asks questions against permitted collections.",
  viewer: "Read-only access to documents and answers.",
};
