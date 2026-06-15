"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { createDocument } from "@/lib/api/assistant";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import { SandboxStatusPill } from "./SandboxStatusPill";

const ASSISTANT_LOGO_URL =
  "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=LumenResearch&backgroundColor=fff3ed";

/**
 * Page-level header for the assistant. Sandbox / Show preview / Ready
 * are now part of the global AppShell header (see AssistantTopControls);
 * this header is intentionally narrow: just the title and a "New"
 * session shortcut.
 */
export function AssistantHeader() {
  const { state, reset } = useAssistantStore();
  const { token } = useAuth();
  const router = useRouter();
  const [creating, setCreating] = useState(false);

  const onNew = async () => {
    if (!token || creating) return;
    setCreating(true);
    reset();
    try {
      const doc = await createDocument(token);
      router.push(`/assistant/${doc.project_id}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <header className="flex items-center gap-2 border-b border-hairline bg-canvas px-3 py-1.5 md:px-4">
      <button
        onClick={onNew}
        disabled={!token || creating}
        className="shrink-0 text-[11px] font-semibold text-charcoal hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
        title="Start a new session"
      >
        {creating ? "Creating..." : "+ New"}
      </button>
      <div
        className="hidden h-7 w-7 shrink-0 rounded-full border border-hairline bg-surface-card bg-cover bg-center sm:block"
        role="img"
        aria-label="Lumen assistant"
        style={{ backgroundImage: `url(${ASSISTANT_LOGO_URL})` }}
      />
      <h1 className="font-display text-[13px] font-semibold text-ink truncate md:text-sm">
        {state.documentTitle || "New assistant session"}
      </h1>
      {state.documentVersion > 0 && (
        <span className="text-[11px] text-charcoal/70">v{state.documentVersion}</span>
      )}
      <div className="flex-1" />
      <SandboxStatusPill compact />
    </header>
  );
}
