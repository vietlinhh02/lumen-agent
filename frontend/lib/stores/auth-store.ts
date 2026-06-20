"use client";

import { useSyncExternalStore } from "react";
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { apiFetch } from "@/lib/api";
import { TOKEN_KEY } from "@/lib/jwt";

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

interface RegisterResponse {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
}

interface AuthState {
  // State
  token: string | null;
  user: AuthUser | null;
  isSubmitting: boolean;

  // Actions
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setUser: (user: AuthUser | null) => void;
  setSubmitting: (v: boolean) => void;
  fetchMe: () => Promise<AuthUser | null>;
  clearAuth: () => void;
}

type PersistedAuthState = Partial<Pick<AuthState, "token" | "user">>;

function getTokenCookieMaxAge(token: string): number {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return 60 * 60 * 24 * 7;
    const payload = JSON.parse(atob(parts[1]));
    const exp = typeof payload.exp === "number" ? payload.exp : null;
    if (!exp) return 60 * 60 * 24 * 7;
    return Math.max(0, exp - Math.floor(Date.now() / 1000));
  } catch {
    return 60 * 60 * 24 * 7;
  }
}

function setTokenCookie(token: string | null) {
  if (typeof document === "undefined") return;
  if (token) {
    const maxAge = getTokenCookieMaxAge(token);
    document.cookie = `${TOKEN_KEY}=${token}; path=/; max-age=${maxAge}`;
  } else {
    document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`;
  }
}

function getFallbackToken(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * `useAuthHydrated` — returns `true` once the persist middleware has
 * finished rehydrating from localStorage. Components should wait for
 * this before reading `token`/`user` so they don't see the empty
 * initial state and bounce a logged-in user to /login on refresh.
 */
export function useAuthHydrated(): boolean {
  return useSyncExternalStore(
    (callback) => {
      const unsubscribeStart = useAuthStore.persist.onHydrate(callback);
      const unsubscribeFinish =
        useAuthStore.persist.onFinishHydration(callback);
      return () => {
        unsubscribeStart();
        unsubscribeFinish();
      };
    },
    () => useAuthStore.persist.hasHydrated(),
    () => false,
  );
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isSubmitting: false,

      async login(email, password) {
        const data = await apiFetch<TokenResponse>("/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        localStorage.setItem(TOKEN_KEY, data.access_token);
        setTokenCookie(data.access_token);
        set({ token: data.access_token });
        // Fetch user profile
        try {
          const user = await apiFetch<AuthUser>("/auth/me", {
            headers: { Authorization: `Bearer ${data.access_token}` },
          });
          set({ user });
        } catch {
          // ignore – we still have the token
        }
      },

      async register(email, password) {
        await apiFetch<RegisterResponse>("/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
      },

      logout() {
        localStorage.removeItem(TOKEN_KEY);
        setTokenCookie(null);
        set({ token: null, user: null });
      },

      setUser(user) {
        set({ user });
      },

      setSubmitting(v) {
        set({ isSubmitting: v });
      },

      async fetchMe() {
        const { token } = get();
        if (!token) return null;
        try {
          const u = await apiFetch<AuthUser>("/auth/me", {
            headers: { Authorization: `Bearer ${token}` },
          });
          set({ user: u });
          return u;
        } catch {
          return null;
        }
      },

      clearAuth() {
        localStorage.removeItem(TOKEN_KEY);
        setTokenCookie(null);
        set({ token: null, user: null });
      },
    }),
    {
      name: "lumen-auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ token: s.token, user: s.user }),
      merge: (persistedState, currentState) => {
        const persisted = persistedState as PersistedAuthState | undefined;
        return {
          ...currentState,
          ...persisted,
          token: persisted?.token ?? getFallbackToken(),
        };
      },
      onRehydrateStorage: () => (state) => {
        setTokenCookie(state?.token ?? null);
      },
    },
  ),
);

/** Backwards-compatible hook alias – same type as the underlying store */
export const useAuth = useAuthStore;
