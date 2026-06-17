/**
 * SessionList - Left sidebar showing all assistant sessions.
 */

"use client";

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { useAuthStore } from "@/lib/stores/auth-store";
import {
  X,
  Plus,
  ChatCircle,
  Trash,
  Clock,
} from "@phosphor-icons/react";
import { relativeTime } from "@/lib/utils";
import { DeleteSessionModal } from "./DeleteSessionModal";

interface SessionListProps {
  onClose: () => void;
  onNewChat: () => void;
  onSelectSession?: () => void;
  /**
   * When true, hides the "Assistant" header row (with the new-chat and
   * close buttons). Useful when the list is embedded inside a parent
   * drawer that already provides its own header and close affordance.
   */
  compact?: boolean;
  /**
   * True when the *active* session is brand-new (no events yet). When
   * true, the "New" button is disabled to prevent the user from
   * spamming the API by creating one empty session after another.
   */
  isCurrentSessionNew?: boolean;
  /**
   * True while a `createSession` call is already in flight (used as an
   * additional re-entrancy guard for rapid clicks).
   */
  isCreating?: boolean;
}

export function SessionList({
  onClose,
  onNewChat,
  onSelectSession,
  compact,
  isCurrentSessionNew = false,
  isCreating = false,
}: SessionListProps) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const sessions = useAssistantStore((s) => s.sessions);
  const activeSessionId = useAssistantStore((s) => s.activeSessionId);
  const loadSessions = useAssistantStore((s) => s.loadSessions);
  const selectSession = useAssistantStore((s) => s.selectSession);

  // Delete modal state
  const [deleteModalSession, setDeleteModalSession] = useState<{
    id: string;
    title: string;
  } | null>(null);

  // Track whether we're mounted on the client (needed for createPortal
  // because `document` is undefined during SSR).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!token) return;
    void loadSessions();
  }, [token, loadSessions]);

  // Re-render every 30s so relativeTime("just now") → "1m ago" → etc.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const handleSelectSession = async (sessionId: string) => {
    await selectSession(sessionId);
    router.push(`/assistant/sessions/${sessionId}`);
    onSelectSession?.();
  };

  const handleNewSession = () => {
    // Hard-stop: don't allow creating while a session is being
    // created or when the current one is still empty.
    if (isCreating || isCurrentSessionNew) return;
    onNewChat();
  };

  const handleDeleteSession = (e: React.MouseEvent, session: { id: string; title: string | null }) => {
    e.stopPropagation();
    setDeleteModalSession({ id: session.id, title: session.title || "New Chat" });
  };

  // Inline rename state — keyed by session id so each row can edit
  // independently without interfering with siblings.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const renameSession = useAssistantStore((s) => s.renameSession);

  const startRename = (
    e: React.MouseEvent,
    session: { id: string; title: string | null }
  ) => {
    e.stopPropagation();
    setEditingId(session.id);
    setDraftTitle(session.title || "");
  };

  const commitRename = (sessionId: string) => {
    const next = draftTitle.trim();
    setEditingId(null);
    if (next) {
      void renameSession(sessionId, next);
    }
  };

  const newButtonDisabled = isCreating || isCurrentSessionNew;
  const newButtonTitle = isCurrentSessionNew
    ? "You're already on a new chat — type a message first"
    : isCreating
      ? "Creating chat…"
      : "New chat";

  return (
    <div
      className="flex flex-col h-full bg-canvas"
      style={compact ? undefined : { borderRight: "1px solid var(--hairline)" }}
    >
      {/* Header */}
      {compact ? (
        <div
          className="flex items-center justify-between h-12 px-4 border-b"
          style={{ borderColor: "var(--hairline)" }}
        >
          <div className="flex items-center gap-2">
            <ChatCircle size={18} className="text-primary" weight="duotone" />
            <span className="font-ui font-medium text-sm text-ink">
              Recent chats
            </span>
          </div>
          <button
            onClick={handleNewSession}
            disabled={newButtonDisabled}
            className={`flex h-8 items-center gap-1 rounded-lg px-2 transition-all duration-150 active:scale-95 ${
              newButtonDisabled
                ? "opacity-40 cursor-not-allowed"
                : "text-charcoal hover:text-ink hover:bg-surface-bone"
            }`}
            title={newButtonTitle}
            aria-label="New chat"
          >
            <Plus size={16} weight="bold" />
            <span className="font-ui text-xs font-medium">New</span>
          </button>
        </div>
      ) : (
        <div
          className="flex items-center justify-between h-14 px-4 border-b"
          style={{ borderColor: "var(--hairline)" }}
        >
          <div className="flex items-center gap-2">
            <ChatCircle size={20} className="text-primary" weight="duotone" />
            <span className="font-ui font-medium text-sm text-ink">
              Assistant
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={handleNewSession}
              disabled={newButtonDisabled}
              className={`flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-150 active:scale-95 ${
                newButtonDisabled
                  ? "opacity-40 cursor-not-allowed"
                  : "text-charcoal hover:text-ink hover:bg-surface-bone"
              }`}
              title={newButtonTitle}
              aria-label="New chat"
            >
              <Plus size={18} weight="bold" />
            </button>
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-charcoal hover:text-ink hover:bg-surface-bone transition-all duration-150 active:scale-95"
              title="Close sidebar"
              aria-label="Close sidebar"
            >
              <X size={18} />
            </button>
          </div>
        </div>
      )}

      {/* Session List */}
      <div className="flex-1 overflow-y-auto py-2 px-2">
        {sessions.length === 0 ? (
          <div className="text-center py-8 px-4">
            <ChatCircle
              size={32}
              className="mx-auto mb-3 text-charcoal/50"
              weight="duotone"
            />
            <p className="font-ui text-xs text-charcoal">
              No chats yet. Start a new conversation!
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {sessions.map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <div
                  key={session.id}
                  onClick={() => handleSelectSession(session.id)}
                  className={`group relative flex items-start gap-2 rounded-lg p-3 pr-9 cursor-pointer transition-all duration-150 active:scale-[0.98] ${
                    isActive
                      ? "bg-primary/10"
                      : "hover:bg-surface-bone"
                  }`}
                >
                  <ChatCircle
                    size={18}
                    className={`mt-0.5 flex-shrink-0 ${
                      isActive ? "text-primary" : "text-charcoal"
                    }`}
                    weight={isActive ? "fill" : "regular"}
                  />
                  <div className="flex-1 min-w-0">
                    {editingId === session.id ? (
                      <input
                        autoFocus
                        value={draftTitle}
                        onChange={(e) => setDraftTitle(e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        onBlur={() => commitRename(session.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            commitRename(session.id);
                          } else if (e.key === "Escape") {
                            setEditingId(null);
                          }
                        }}
                        maxLength={200}
                        className="font-ui text-sm w-full rounded border border-primary/40 bg-canvas px-1 py-0.5 text-ink focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                    ) : (
                      <p
                        onDoubleClick={(e) => startRename(e, session)}
                        className={`font-ui text-sm truncate cursor-text ${
                          isActive ? "text-primary font-medium" : "text-ink"
                        }`}
                        title="Double-click to rename"
                      >
                        {session.title || "Untitled"}
                      </p>
                    )}
                    <div className="flex items-center gap-1 mt-0.5">
                      <Clock size={11} className="text-charcoal/60" />
                      <span className="font-ui text-[11px] text-charcoal/60" key={tick}>
                        {relativeTime(session.updated_at)}
                      </span>
                    </div>
                    {session.project_title && (
                      <p className="font-ui text-[11px] text-charcoal/60 truncate mt-0.5">
                        {session.project_title}
                      </p>
                    )}
                  </div>

                  {/* Delete button — always visible on touch devices
                      (no hover), shown on hover on desktop. */}
                  <button
                    onClick={(e) => handleDeleteSession(e, session)}
                    className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded text-charcoal hover:text-red-500 hover:bg-surface-bone transition-all duration-150 opacity-100 lg:opacity-0 lg:group-hover:opacity-100 active:scale-90"
                    title="Delete chat"
                    aria-label="Delete chat"
                  >
                    <Trash size={14} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Delete Session Modal — rendered via portal to document.body so it
          is NOT clipped by the parent dropdown's `overflow-hidden` or
          affected by its `transform` (which would otherwise create a new
          containing block for `position: fixed` descendants). */}
      {mounted && deleteModalSession
        ? createPortal(
            <DeleteSessionModal
              sessionId={deleteModalSession.id}
              sessionTitle={deleteModalSession.title}
              onClose={() => setDeleteModalSession(null)}
            />,
            document.body,
          )
        : null}
    </div>
  );
}
