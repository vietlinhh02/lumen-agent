"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isTokenExpired } from "@/lib/jwt";
import { useAuthStore, useAuthHydrated } from "@/lib/stores/auth-store";

export function LoginGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const hasValidToken = Boolean(token && !isTokenExpired(token));
  // Same hydration caveat as `(app)/layout.tsx`: on a hard refresh the
  // zustand `persist` middleware needs a tick to load the token back
  // from localStorage. If we evaluate the redirect synchronously the
  // user is always seen as logged-out and bounced to /login.
  const hydrated = useAuthHydrated();

  useEffect(() => {
    if (!hydrated) return;
    if (hasValidToken) {
      router.replace("/projects");
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
