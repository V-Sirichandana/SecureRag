"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Organization, Role } from "@/lib/types";

interface UIState {
  sidebarCollapsed: boolean;
  mobileSidebarOpen: boolean;
  commandPaletteOpen: boolean;
  activeOrganizationId: string;
  role: Role;
  toggleSidebar: () => void;
  setSidebarCollapsed: (value: boolean) => void;
  setMobileSidebarOpen: (value: boolean) => void;
  setCommandPaletteOpen: (value: boolean) => void;
  setActiveOrganization: (id: string) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      mobileSidebarOpen: false,
      commandPaletteOpen: false,
      activeOrganizationId: "org_acme",
      role: "owner",
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (value) => set({ sidebarCollapsed: value }),
      setMobileSidebarOpen: (value) => set({ mobileSidebarOpen: value }),
      setCommandPaletteOpen: (value) => set({ commandPaletteOpen: value }),
      setActiveOrganization: (id) => set({ activeOrganizationId: id }),
    }),
    {
      name: "securerag-ui",
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        activeOrganizationId: state.activeOrganizationId,
      }),
    },
  ),
);

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  role: Role;
  department: string;
  organizationId: string;
}

interface AuthState {
  user: SessionUser | null;
  organizations: Organization[];
  login: (user: SessionUser, organizations: Organization[]) => void;
  logout: () => void;
  updateUser: (patch: Partial<SessionUser>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      organizations: [],
      login: (user, organizations) => set({ user, organizations }),
      logout: () => set({ user: null, organizations: [] }),
      updateUser: (patch) =>
        set((state) => (state.user ? { user: { ...state.user, ...patch } } : state)),
    }),
    { name: "securerag-auth" },
  ),
);
