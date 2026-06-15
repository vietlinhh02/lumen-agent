"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { createDocument } from "@/lib/api/assistant";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import { StatusBadge } from "./StatusBadge";

const ASSISTANT_LOGO_URL =
  "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=LumenResearch&backgroundColor=fff3ed";

interface Props {
  onTogglePreview: () => void;
  previewOpen: boolean;
  hasDoc: boolean;
}

export function AssistantHeader({ onTogglePreview, previewOpen, hasDoc }: Props) {
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
    <header className="flex items-center justify-between gap-2 border-b border-hairline bg-canvas px-3 py-2 md:px-6 md:py-3">
      <div className="flex items-center gap-2 min-w-0 md:gap-3">
        <button
          onClick={onNew}
          disabled={!token || creating}
          className="shrink-0 text-xs text-charcoal hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
          title="Start a new session"
        >
          {creating ? "Creating..." : "New"}
        </button>
        <div
          className="hidden h-9 w-9 shrink-0 rounded-full border border-hairline bg-surface-card bg-cover bg-center sm:block"
          role="img"
          aria-label="Lumen assistant"
          style={{ backgroundImage: `url(${ASSISTANT_LOGO_URL})` }}
        />
        <h1 className="font-display text-sm font-semibold text-ink truncate md:text-base">
          {state.documentTitle || "New assistant session"}
        </h1>
        {state.documentVersion > 0 && (
          <span className="text-xs text-charcoal">v{state.documentVersion}</span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2 md:gap-3">
        <button
          onClick={onTogglePreview}
          disabled={!hasDoc}
          className="rounded-full border border-hairline bg-surface-card px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-hairline-strong disabled:opacity-40 disabled:cursor-not-allowed md:px-3"
          title={hasDoc ? "Toggle Markdown preview" : "Preview appears once a document is generated"}
        >
          <span className="hidden sm:inline">{previewOpen ? "Hide preview" : "Show preview"}</span>
          <span className="sm:hidden">{previewOpen ? "Chat" : "Doc"}</span>
        </button>
        <StatusBadge status={state.agentStatus} connected={state.sseConnected} />
      </div>
    </header>
  );
}
