"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { useAuthStore, useAuthHydrated } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { isTokenExpired } from "@/lib/jwt";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const fetchProjects = useProjectsStore((s) => s.fetchProjects);
  // Zustand v5 `persist` rehydrates from localStorage *asynchronously*,
  // so on the first render `token` is still null. If we run the auth
  // check before hydration completes, we'll wipe the persisted token via
  // `clearAuth()` and bounce the user to /login on every refresh. The
  // `hydrated` flag (from `useAuthHydrated`) lets us wait for
  // rehydration before deciding.
  const hydrated = useAuthHydrated();

  const user = useAuthStore((s) => s.user);
  const fetchMe = useAuthStore((s) => s.fetchMe);

  useEffect(() => {
    if (!hydrated) return;
    if (!token || isTokenExpired(token)) {
      clearAuth();
      router.replace("/login");
      return;
    }
    if (!user) {
      void fetchMe();
    }
    // Pre-fetch the projects list once after auth – every page that needs
    // it (projects, matrix, gaps, reports, search, …) will then render
    // immediately from the in-memory cache instead of triggering its own
    // request.
    void fetchProjects();
  }, [clearAuth, fetchProjects, fetchMe, hydrated, router, token, user]);

  if (!hydrated || !token || isTokenExpired(token)) {
    return (
      <div className="flex h-screen items-center justify-center bg-canvas">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
