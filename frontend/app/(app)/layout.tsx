"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { isTokenExpired } from "@/lib/jwt";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const fetchProjects = useProjectsStore((s) => s.fetchProjects);
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    if (!token || isTokenExpired(token)) {
      clearAuth();
      router.replace("/login");
      return;
    }
    setAuthorized(true);
    // Pre-fetch the projects list once after auth – every page that needs
    // it (projects, matrix, gaps, reports, search, …) will then render
    // immediately from the in-memory cache instead of triggering its own
    // request.
    void fetchProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, router, clearAuth]);

  if (!authorized || !token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
