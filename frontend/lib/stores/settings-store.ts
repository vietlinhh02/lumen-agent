"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import type { UserProfile, AdminUser } from "@/lib/types";

type SettingsTab = "profile" | "admin";

interface SettingsState {
  // State
  activeTab: SettingsTab;
  profile: UserProfile | null;
  isAdmin: boolean;
  loadingProfile: boolean;
  users: AdminUser[];
  loadingUsers: boolean;

  // Actions
  setActiveTab: (t: SettingsTab) => void;
  fetchProfile: () => Promise<void>;
  updateProfileName: (displayName: string) => Promise<UserProfile | null>;
  fetchUsers: () => Promise<void>;
  toggleUserActive: (userId: string, currentActive: boolean) => Promise<AdminUser | null>;
  changePassword: (current: string, next: string) => Promise<boolean>;
  reset: () => void;
}

export const useSettingsStore = create<SettingsState>()((set, get) => ({
  activeTab: "profile",
  profile: null,
  isAdmin: false,
  loadingProfile: false,
  users: [],
  loadingUsers: false,

  setActiveTab(t) {
    set({ activeTab: t });
  },

  async fetchProfile() {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loadingProfile: true });
    try {
      const u = await apiFetch<UserProfile>("/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
      });
      set({ profile: u, isAdmin: u.role === "admin" });
      useAuthStore.getState().setUser(u);
    } finally {
      set({ loadingProfile: false });
    }
  },

  async updateProfileName(displayName) {
    const token = useAuthStore.getState().token;
    if (!token) return null;
    try {
      const updated = await apiFetch<UserProfile>("/auth/profile", {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ display_name: displayName }),
      });
      set({ profile: updated, isAdmin: updated.role === "admin" });
      useAuthStore.getState().setUser(updated);
      return updated;
    } catch {
      return null;
    }
  },

  async fetchUsers() {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loadingUsers: true });
    try {
      const data = await apiFetch<{ items: AdminUser[]; total: number }>(
        "/admin/users",
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ users: data.items || [] });
    } finally {
      set({ loadingUsers: false });
    }
  },

  async toggleUserActive(userId, currentActive) {
    const token = useAuthStore.getState().token;
    if (!token) return null;
    try {
      const updated = await apiFetch<AdminUser>(`/admin/users/${userId}`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ is_active: !currentActive }),
      });
      set({
        users: get().users.map((u) => (u.id === userId ? updated : u)),
      });
      return updated;
    } catch {
      return null;
    }
  },

  async changePassword(current, next) {
    const token = useAuthStore.getState().token;
    if (!token) return false;
    try {
      await apiFetch("/auth/password", {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          current_password: current,
          new_password: next,
        }),
      });
      return true;
    } catch {
      return false;
    }
  },

  reset() {
    set({
      activeTab: "profile",
      profile: null,
      isAdmin: false,
      loadingProfile: false,
      users: [],
      loadingUsers: false,
    });
  },
}));
