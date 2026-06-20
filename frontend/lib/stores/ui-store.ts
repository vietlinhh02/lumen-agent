"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

type Theme = "light" | "dark";

interface UIState {
  // State
  theme: Theme;
  sidebarMobileOpen: boolean;
  userMenuOpen: boolean;
  /**
   * Whether the assistant "tool panel" (right side) is open.
   * Controlled by a button in the AppShell header, so it lives in the
   * global UI store rather than the per-page component state.
   */
  assistantToolPanelOpen: boolean;
  /**
   * Whether the assistant "sessions" dropdown (in the AppShell header)
   * is open.
   */
  assistantSessionsOpen: boolean;
  /**
   * Whether the header "Switch project" dropdown is open. Lives here so
   * outside-click handlers in AppShell can mutate it cleanly.
   */
  projectSwitcherOpen: boolean;

  // Actions
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  setSidebarMobileOpen: (v: boolean) => void;
  setUserMenuOpen: (v: boolean) => void;
  toggleUserMenu: () => void;
  toggleSidebar: () => void;
  closeSidebar: () => void;
  setAssistantToolPanelOpen: (v: boolean) => void;
  toggleAssistantToolPanel: () => void;
  setAssistantSessionsOpen: (v: boolean) => void;
  toggleAssistantSessions: () => void;
  setProjectSwitcherOpen: (v: boolean) => void;
}

function applyTheme(t: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", t === "dark");
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      theme: "light",
      sidebarMobileOpen: false,
      userMenuOpen: false,
      assistantToolPanelOpen: false,
      assistantSessionsOpen: true,
      projectSwitcherOpen: false,

      setTheme(t) {
        applyTheme(t);
        set({ theme: t });
      },
      toggleTheme() {
        const next: Theme = get().theme === "light" ? "dark" : "light";
        applyTheme(next);
        set({ theme: next });
      },

      setSidebarMobileOpen(v) {
        set({ sidebarMobileOpen: v });
      },
      toggleSidebar() {
        set({ sidebarMobileOpen: !get().sidebarMobileOpen });
      },
      closeSidebar() {
        set({ sidebarMobileOpen: false });
      },

      setUserMenuOpen(v) {
        set({ userMenuOpen: v });
      },
      toggleUserMenu() {
        set({ userMenuOpen: !get().userMenuOpen });
      },

      setAssistantToolPanelOpen(v) {
        set({ assistantToolPanelOpen: v });
      },
      toggleAssistantToolPanel() {
        set({ assistantToolPanelOpen: !get().assistantToolPanelOpen });
      },
      setAssistantSessionsOpen(v) {
        set({ assistantSessionsOpen: v });
      },
      toggleAssistantSessions() {
        set({ assistantSessionsOpen: !get().assistantSessionsOpen });
      },
      setProjectSwitcherOpen(v) {
        set({ projectSwitcherOpen: v });
      },
    }),
    {
      name: "lumen-ui",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ theme: s.theme }),
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.theme);
      },
    },
  ),
);
