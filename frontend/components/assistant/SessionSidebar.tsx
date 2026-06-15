"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { useAuth } from "@/lib/auth";
import { createDocument, listDocuments } from "@/lib/api/assistant";
import type { ChatDocumentListResponse } from "@/lib/types";

interface Props {
  activeProjectId: string | null;
  onSelect?: () => void;
}

const EMPTY: ChatDocumentListResponse = { items: [], total: 0 };

export function SessionSidebar({ activeProjectId, onSelect }: Props) {
  const { token } = useAuth();
  const router = useRouter();
  const [creating, setCreating] = useState(false);

  const swrKey = token ? ["assistant-documents", token] : null;
  const { data, isLoading } = useSWR<ChatDocumentListResponse>(
    swrKey,
    ([, t]) => listDocuments(t as string),
    { fallbackData: EMPTY, revalidateOnFocus: false },
  );

  const goNew = async () => {
    if (!token || creating) return;
    setCreating(true);
    onSelect?.();
    try {
      const doc = await createDocument(token);
      router.push(`/assistant/${doc.project_id}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <aside className="h-14 w-full shrink-0 border-b border-hairline bg-surface-bone/40 flex md:h-auto md:w-56 md:border-b-0 md:border-r md:flex-col">
      <div className="shrink-0 px-2 sm:px-3 py-2 border-r border-hairline md:border-r-0 md:border-b flex items-center justify-between gap-2">
        <span className="hidden md:inline text-xs font-semibold uppercase tracking-wide text-charcoal">
          Sessions
        </span>
        <button
          onClick={goNew}
          disabled={!token || creating}
          className="h-9 rounded-full bg-primary text-on-primary text-xs px-3 font-semibold hover:bg-primary-deep disabled:cursor-not-allowed disabled:opacity-50"
          title="Start a new session"
        >
          <span className="md:hidden">{creating ? "..." : "+"}</span>
          <span className="hidden md:inline">{creating ? "Creating..." : "+ New"}</span>
        </button>
      </div>
      <div className="flex-1 overflow-x-auto overflow-y-hidden md:overflow-x-hidden md:overflow-y-auto flex md:block">
        {isLoading && (
          <div className="px-3 py-3 text-xs text-charcoal/70 whitespace-nowrap">Loading…</div>
        )}
        {!isLoading && data && data.items.length === 0 && (
          <div className="px-3 py-3 text-xs text-charcoal/70 whitespace-nowrap">
            No past sessions yet. Start a new chat to create one.
          </div>
        )}
        {data?.items.map((doc) => {
          const isActive = doc.project_id === activeProjectId;
          return (
            <button
              key={doc.id}
              onClick={() => router.push(`/assistant/${doc.project_id}`)}
              title={doc.title || "Untitled"}
              className={`h-14 min-w-14 max-w-40 md:h-auto md:min-w-0 md:max-w-none md:w-full text-left px-3 py-2 border-r md:border-r-0 md:border-b border-hairline hover:bg-canvas ${
                isActive ? "bg-canvas border-t-2 border-t-primary md:border-t-0 md:border-l-2 md:border-l-primary" : ""
              }`}
            >
              <div className="text-sm font-medium text-ink truncate">
                <span className="md:hidden">
                  {(doc.title || "U").charAt(0).toUpperCase()}
                </span>
                <span className="hidden md:inline">{doc.title || "Untitled"}</span>
              </div>
              <div className="hidden md:block text-xs text-charcoal/70 truncate">
                v{doc.version} · {new Date(doc.updated_at).toLocaleDateString()}
              </div>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
