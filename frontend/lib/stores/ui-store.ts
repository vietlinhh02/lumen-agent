"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

type Theme = "light" | "dark";

interface UIState {
  // State
  theme: Theme;
  sidebarMobileOpen: boolean;
  userMenuOpen: boolean;

  // Actions
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  setSidebarMobileOpen: (v: boolean) => void;
  setUserMenuOpen: (v: boolean) => void;
  toggleUserMenu: () => void;
  toggleSidebar: () => void;
  closeSidebar: () => void;
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
