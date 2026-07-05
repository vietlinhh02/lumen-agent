"use client";

import { useAuthStore } from "@/lib/stores/auth-store";

function getDisplayName(displayName: string | null, email: string | undefined): string {
  if (displayName) return displayName;
  if (!email) return "there";
  return email.split("@")[0] || "there";
}

export function ChatEmptyState() {
  const user = useAuthStore((s) => s.user);
  const name = getDisplayName(user?.display_name ?? null, user?.email);

  return (
    <div className="w-full text-center mb-8 select-none animate-fade-in">
      <h1 className="font-display text-[28px] sm:text-[36px] font-semibold tracking-tight text-ink leading-tight">
        Hello, {name}!
      </h1>
      <p className="mt-1.5 text-ash font-ui text-sm">
        What can I help you with today?
      </p>
    </div>
  );
}
