"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isTokenExpired } from "@/lib/jwt";
import { useAuthHydrated, useAuthStore } from "@/lib/stores/auth-store";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const hydrated = useAuthHydrated();
  const hasValidToken = Boolean(token && !isTokenExpired(token));

  useEffect(() => {
    if (!hydrated) return;
    if (hasValidToken) {
      router.replace("/dashboard");
    }
  }, [hasValidToken, hydrated, router]);

  if (!hydrated || hasValidToken) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}
