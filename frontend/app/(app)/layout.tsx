"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { useAuthStore } from "@/lib/stores/auth-store";
import { isTokenExpired } from "@/lib/jwt";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    if (!token || isTokenExpired(token)) {
      clearAuth();
      router.replace("/login");
      return;
    }
    setAuthorized(true);
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
