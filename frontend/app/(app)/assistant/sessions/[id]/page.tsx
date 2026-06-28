/**
 * Assistant session chat page.
 *
 * Layout:
 * - Center: chat stream + chat input
 * - Right: tool panel (slide-in / drawer), toggled from the AppShell header
 *
 * The session list, "New chat" button and "View tool" toggle all live in
 * the AppShell header (see <AssistantHeaderControls />). The project picker
 * lives in the chat input area (see <ChatProjectPicker />). This page only
 * renders the chat surface and the right-hand tool panel.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAssistantStore, useMessages } from "@/lib/stores/assistant-store";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useUIStore } from "@/lib/stores/ui-store";
import { ChatMessage } from "@/components/assistant";
import { ChatBox } from "@/components/assistant/ChatBox";
import { ToolPanel } from "@/components/assistant/ToolPanel";

import { SessionList } from "@/components/assistant/SessionList";
import type {
  MessageEvent,
} from "@/lib/types/assistant";
import {
  PaperPlaneTilt,
  Folder,
} from "@phosphor-icons/react";

export default function AssistantSessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const selectSession = useAssistantStore((s) => s.selectSession);
  const activeSessionId = useAssistantStore((s) => s.activeSessionId);
  const isStreaming = useAssistantStore((s) => s.isStreaming);
  const loadSessions = useAssistantStore((s) => s.loadSessions);
  const createSession = useAssistantStore((s) => s.createSession);
  const events = useAssistantStore((s) => s.events);
  const currentSession = useAssistantStore((s) => s.currentSession);

  // Tool panel state lives in the global UI store
  const toolPanelOpen = useUIStore((s) => s.assistantToolPanelOpen);
  const setToolPanelOpen = useUIStore((s) => s.setAssistantToolPanelOpen);

  const [jumpToLatest, setJumpToLatest] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Load sessions (the project picker in the chat input triggers its own
  // fetchProjects call so the page itself doesn't need to do it).
  useEffect(() => {
    if (!token) return;
    void loadSessions();
  }, [token, loadSessions]);

  useEffect(() => {
    if (!sessionId) return;
    if (sessionId === activeSessionId && currentSession && currentSession.id === sessionId) return;
    void selectSession(sessionId);
  }, [sessionId, activeSessionId, currentSession, selectSession]);

  // Scroll to bottom when new events arrive
  useEffect(() => {
    if (!sessionId) return;
    const sessionEvents = events.get(sessionId) ?? [];
    const lastEvent = sessionEvents[sessionEvents.length - 1];

    if (lastEvent && !jumpToLatest) {
      // Auto-scroll for user messages, thought streams, and completions
      if (
        lastEvent.type === "message" ||
        lastEvent.type === "thought" ||
        lastEvent.type === "done"
      ) {
        containerRef.current?.scrollTo({
          top: containerRef.current.scrollHeight,
          behavior: "auto", // Instant snap during streaming avoids latency and layout jitter
        });
      }
    }
  }, [events, sessionId, jumpToLatest]);

  // Detect manual scroll for "Jump to latest" button
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
    setJumpToLatest(!isNearBottom);
  };

  // Get events for current session (for audit/activity panel)
  const sessionEvents = sessionId ? (events.get(sessionId) ?? []) : [];
  // Get messages for stable chat rendering (separate from audit events)
  const messages = useMessages();
  const userName = getUserDisplayName(user?.email);

  // Build chat items from messages (stable, no array index keys)
  const chatItems: {
    type: "message";
    id: string;
    message: MessageEvent;
    isStreaming: boolean;
  }[] = [];

  const latestAssistantMessageByTurn = new Map<string, string>();
  for (const msg of messages) {
    if (msg?.role !== "assistant" || !msg.id) {
      continue;
    }
    const turnKey = msg.turn_id ?? `message:${msg.id}`;
    latestAssistantMessageByTurn.set(turnKey, msg.id);
  }

  // First, add messages from messagesBySession (stable chat transcript)
  // Dedupe by ID to prevent React duplicate key errors
  const seenMessageIds = new Set<string>();
  for (const msg of messages) {
    // Defensive: skip nullish entries — can happen briefly when a streaming
    // message is replaced and React captures an in-between state.
    if (!msg || !msg.id) {
      continue;
    }
    // Skip if we've already added this message
    if (seenMessageIds.has(msg.id)) {
      continue;
    }
    if (msg.role === "assistant") {
      const turnKey = msg.turn_id ?? `message:${msg.id}`;
      if (latestAssistantMessageByTurn.get(turnKey) !== msg.id) {
        continue;
      }
    }
    seenMessageIds.add(msg.id);

    // Check if this is a streaming assistant message (last event is this message and streaming)
    const lastMsg = messages[messages.length - 1];
    const isStreamingMessage =
      isStreaming &&
      messages.length > 0 &&
      lastMsg &&
      lastMsg.id === msg.id &&
      msg.role === "assistant";

    chatItems.push({
      type: "message",
      id: msg.id, // Use stable message ID as key
      message: msg,
      isStreaming: isStreamingMessage,
    });
  }

  const currentSessionEventCount = activeSessionId
    ? (events.get(activeSessionId)?.length ?? 0)
    : 0;
  const isCurrentSessionNew = activeSessionId !== null && currentSessionEventCount === 0;

  const handleNewChat = async () => {
    if (isCreating) return;
    if (isCurrentSessionNew) return;

    setIsCreating(true);
    try {
      const session = await createSession();
      if (session) router.push(`/assistant/sessions/${session.id}`);
    } finally {
      setIsCreating(false);
    }
  };

  // Handle send message
  const handleSend = async (message: string) => {
    const store = useAssistantStore.getState();
    await store.sendMessage(message);
  };

  // Handle stop
  const handleStop = () => {
    const store = useAssistantStore.getState();
    store.stopStream();
  };

  if (!token) {
    return null;
  }

  return (
    <div className="relative flex h-full min-h-0">
      {/* Left Collapsible Sessions Panel (desktop only) */}
      <aside
        data-tour="assistant-sessions"
        className="hidden xl:block w-64 flex-shrink-0 bg-canvas border-r"
        style={{ borderColor: "var(--hairline)" }}
      >
        <div className="h-full w-64 overflow-y-auto scrollbar-hide">
          <SessionList
            compact
            isCurrentSessionNew={isCurrentSessionNew}
            isCreating={isCreating}
            onClose={() => {}}
            onNewChat={handleNewChat}
            onSelectSession={() => {}}
          />
        </div>
      </aside>

      {/* Mobile backdrop for tool panel */}
      {toolPanelOpen && (
        <button
          type="button"
          className="fixed inset-0 bg-black/40 z-30 lg:hidden"
          onClick={() => setToolPanelOpen(false)}
          aria-label="Close tool panel"
        />
      )}

      {/* Chat area takes the full width; no in-page sidebar/topbar */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Chat Area */}
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className={`min-h-0 flex-1 overflow-y-auto scroll-smooth px-3 py-4 pb-8 sm:px-4 ${
            !toolPanelOpen ? "xl:pr-[256px]" : ""
          }`}
        >
          <div className="relative">
            {/* Chat column - centered in the viewport, full width up to
                3xl breakpoint. */}
            <div className="mx-auto w-full max-w-4xl space-y-4">
                {/* Project context banner — shown when the session is
                    linked to a project so the user always knows which
                    project's papers / matrix / gaps the assistant is
                    reasoning about. This is purely informational; the
                    project link is set in the header and cannot be
                    re-selected once the session is linked. */}
                {currentSession?.project_id && currentSession.project_title && (
                  <div className="flex justify-center pt-4">
                    <div className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1.5 font-ui text-[12px] font-semibold text-primary">
                      <Folder size={12} weight="fill" />
                      <span className="max-w-[260px] truncate">
                        {currentSession.project_title}
                      </span>
                    </div>
                  </div>
                )}

                {/* Welcome message if no events */}
                {chatItems.length === 0 && (
                  <div data-tour="assistant-welcome" className="text-center py-12">
                    <div className="flex justify-center mb-4">
                      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                        <svg
                          width="32"
                          height="32"
                          viewBox="0 0 32 32"
                          fill="none"
                          className="text-primary"
                        >
                          <path
                            d="M16 4C9.373 4 4 9.373 4 16s5.373 12 12 12 12-5.373 12-12S22.627 4 16 4zm-1.5 18.5v-5h3l-5-7v5h-3l5 7z"
                            fill="currentColor"
                          />
                        </svg>
                      </div>
                    </div>
                    <h2 className="font-display text-xl font-semibold text-ink mb-2">
                      How can I help you today?
                    </h2>
                    <p className="font-ui text-sm text-charcoal max-w-md mx-auto">
                      I can search for papers, save them to your project, generate
                      literature matrices, detect research gaps, and create reports.
                    </p>
                  </div>
                )}

                {/* Messages */}
                {chatItems.map((item) => {
                  const lastAssistantMessage = chatItems
                    .slice()
                    .reverse()
                    .find((candidate) => candidate.message.role === "assistant");
                  const isLastAssistantMessage =
                    item.message.role === "assistant" &&
                    item.id === lastAssistantMessage?.id;

                  return (
                    <ChatMessage
                      key={item.id}
                      event={item.message}
                      userName={userName}
                      allEvents={sessionEvents}
                      isStreaming={item.isStreaming}
                      isLastAssistantMessage={isLastAssistantMessage}
                    />
                  );
                })}

                {/* Streaming indicator */}
                {isStreaming && (
                  <div className="flex items-center gap-2 text-charcoal font-ui text-sm py-2">
                    <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
                    Thinking...
                  </div>
                )}
            </div>



            {/* Jump to latest button */}
            {jumpToLatest && (
              <div className="sticky bottom-3 z-10 flex justify-center animate-bounce">
                <button
                  type="button"
                  onClick={() => {
                    containerRef.current?.scrollTo({
                      top: containerRef.current.scrollHeight,
                      behavior: "smooth",
                    });
                    setJumpToLatest(false);
                  }}
                  className="flex items-center gap-1.5 rounded-full bg-ink px-4 py-2 font-ui text-xs font-medium text-white shadow-lg transition-colors hover:bg-charcoal"
                >
                  <PaperPlaneTilt size={14} />
                  Jump to latest
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Chat Box */}
        <div
          className={`shrink-0 border-t bg-canvas ${!toolPanelOpen ? "xl:pr-[256px]" : ""}`}
          style={{ borderColor: "var(--hairline)" }}
        >
          <div className="max-w-4xl mx-auto px-3 sm:px-4 py-3 sm:py-4">
            <ChatBox onSend={handleSend} onStop={handleStop} onNewChat={handleNewChat} />
          </div>
        </div>
      </div>

      {/* Right Tool Panel (mobile: drawer below the header; desktop: inline panel) */}
      <aside
        className={`${
          toolPanelOpen
            ? "w-80 translate-x-0"
            : "w-0 lg:translate-x-0 translate-x-full"
        } ${
          toolPanelOpen
            ? "fixed top-[60px] right-0 bottom-0 z-40 lg:relative lg:top-0"
            : ""
        } transition-all duration-300 overflow-hidden flex-shrink-0 bg-canvas border-l`}
        style={{ borderColor: "var(--hairline)" }}
      >
        <div className="h-full overflow-y-auto">
          <ToolPanel onClose={() => setToolPanelOpen(false)} />
        </div>
      </aside>
    </div>
  );
}

function getUserDisplayName(email: string | undefined): string {
  if (!email) {
    return "You";
  }

  return email.split("@")[0] || "You";
}
