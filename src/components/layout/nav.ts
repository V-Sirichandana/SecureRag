import {
  BarChart3,
  FolderKanban,
  FileText,
  Gauge,
  KeyRound,
  MessageSquare,
  ScrollText,
  Settings,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const navSections: NavSection[] = [
  {
    title: "Workspace",
    items: [
      { label: "Dashboard", href: "/app/dashboard", icon: Gauge },
      { label: "AI Chat", href: "/app/chat", icon: MessageSquare },
      { label: "Documents", href: "/app/documents", icon: FileText },
      { label: "Collections", href: "/app/collections", icon: FolderKanban },
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Users", href: "/app/users", icon: Users },
      { label: "Roles & Permissions", href: "/app/roles", icon: ShieldCheck },
      { label: "Audit Logs", href: "/app/audit-logs", icon: ScrollText },
    ],
  },
  {
    title: "Developer",
    items: [{ label: "API Keys", href: "/app/api-keys", icon: KeyRound }],
  },
  {
    title: "Analytics",
    items: [{ label: "Usage", href: "/app/usage", icon: BarChart3 }],
  },
  {
    title: "Settings",
    items: [{ label: "Settings", href: "/app/settings", icon: Settings }],
  },
];

export const flatNavItems: NavItem[] = navSections.flatMap((section) => section.items);

const breadcrumbLabels: Record<string, string> = {
  app: "Workspace",
  dashboard: "Dashboard",
  chat: "AI Chat",
  documents: "Documents",
  collections: "Collections",
  users: "Users",
  roles: "Roles & Permissions",
  "audit-logs": "Audit Logs",
  "api-keys": "API Keys",
  usage: "Usage",
  settings: "Settings",
  general: "General",
  security: "Security",
  ai: "AI Configuration",
  notifications: "Notifications",
  billing: "Billing",
};

export interface Breadcrumb {
  label: string;
  href: string;
}

export function buildBreadcrumbs(pathname: string): Breadcrumb[] {
  const segments = pathname.split("/").filter(Boolean);
  const crumbs: Breadcrumb[] = [];
  let current = "";

  for (const segment of segments) {
    current += `/${segment}`;
    const label = breadcrumbLabels[segment] ?? decodeURIComponent(segment);
    if (current === "/app") continue;
    crumbs.push({ label, href: current });
  }

  return crumbs;
}

export function pageTitle(pathname: string): string {
  const crumbs = buildBreadcrumbs(pathname);
  return crumbs[crumbs.length - 1]?.label ?? "Dashboard";
}
