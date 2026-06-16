"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isTokenExpired } from "@/lib/jwt";
import { useAuthStore } from "@/lib/stores/auth-store";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (token && !isTokenExpired(token)) {
      router.replace("/dashboard");
    } else {
      setReady(true);
    }
  }, [token, router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}
