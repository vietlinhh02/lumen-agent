/**
 * Assistant session chat page.
 *
 * Layout:
 * - Left sidebar (xl): Session list
 * - Center: chat stream + Deep Research components
 * - Right: Deep Research terminal panel (shown when research is running)
 *
 * Deep Research flow:
 * 1. User toggles "Deep Research" in ChatBox → sends first message
 * 2. Backend responds with ActionEvent(confirm_project) → ConfirmProjectPanel appears
 * 3. User confirms → backend creates project + DeepResearchJob
 * 4. DeepResearchTerminal shows real-time progress via SSE stream
 * 5. Report streams into chat via AssistantDeltaEvent
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAssistantStore, useMessages, useDeepResearchState, usePendingAction } from "@/lib/stores/assistant-store";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useUIStore } from "@/lib/stores/ui-store";
import { ChatMessage, ChatEmptyState } from "@/components/assistant";
import { ChatBox } from "@/components/assistant/ChatBox";
import { ThinkingPanel } from "@/components/assistant/ThinkingPanel";
import { ConfirmProjectPanel } from "@/components/assistant/ConfirmProjectPanel";
import { DeepResearchTerminal } from "@/components/assistant/DeepResearchTerminal";
import { SessionList } from "@/components/assistant/SessionList";
import type {
  MessageEvent,
} from "@/lib/types/assistant";
import {
  PaperPlaneTilt,
  Folder,
  ArrowsLeftRight,
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

  // Deep research state
  const deepResearchState = useDeepResearchState();
  const pendingAction = usePendingAction();

  const [jumpToLatest, setJumpToLatest] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const sidebarCollapsed = useUIStore((s) => s.assistantSidebarCollapsed);
  const toggleSidebarCollapsed = useUIStore((s) => s.toggleAssistantSidebarCollapsed);
  const isSessionsOpen = useUIStore((s) => s.assistantSessionsOpen);
  const toggleSessions = useUIStore((s) => s.toggleAssistantSessions);

  const handleToggleSidebar = () => {
    if (typeof window !== "undefined" && window.innerWidth < 1280) {
      toggleSessions();
    } else {
      toggleSidebarCollapsed();
    }
  };

  const isCollapsed = typeof window !== "undefined" && window.innerWidth < 1280
    ? !isSessionsOpen
    : sidebarCollapsed;

  const containerRef = useRef<HTMLDivElement>(null);

  // Load sessions
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
      if (
        lastEvent.type === "message" ||
        lastEvent.type === "thought" ||
        lastEvent.type === "done"
      ) {
        containerRef.current?.scrollTo({
          top: containerRef.current.scrollHeight,
          behavior: "auto",
        });
      }
    }
  }, [events, sessionId, jumpToLatest]);

  // Auto-send pending message from empty state suggestion
  useEffect(() => {
    if (!sessionId || !currentSession || activeSessionId !== sessionId) return;

    const pendingMsg = sessionStorage.getItem("pending_initial_message");
    if (pendingMsg) {
      sessionStorage.removeItem("pending_initial_message");
      const timer = setTimeout(() => {
        void handleSend(pendingMsg, false);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [sessionId, currentSession, activeSessionId]);

  // Detect manual scroll for "Jump to latest" button
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
    setJumpToLatest(!isNearBottom);
  };

  // Get events for current session (for audit/activity panel)
  const sessionEvents = sessionId ? (events.get(sessionId) ?? []) : [];
  const messages = useMessages();
  const userName = getUserDisplayName(user?.email);

  // Build chat items from messages
  const chatItems: {
    type: "message";
    id: string;
    message: MessageEvent;
    isStreaming: boolean;
  }[] = [];

  const latestAssistantMessageByTurn = new Map<string, string>();
  for (const msg of messages) {
    if (msg?.role !== "assistant" || !msg.id) continue;
    const turnKey = msg.turn_id ?? `message:${msg.id}`;
    latestAssistantMessageByTurn.set(turnKey, msg.id);
  }

  const seenMessageIds = new Set<string>();
  for (const msg of messages) {
    if (!msg || !msg.id) continue;
    if (seenMessageIds.has(msg.id)) continue;
    if (msg.role === "assistant") {
      const turnKey = msg.turn_id ?? `message:${msg.id}`;
      if (latestAssistantMessageByTurn.get(turnKey) !== msg.id) continue;
    }
    seenMessageIds.add(msg.id);

    const lastMsg = messages[messages.length - 1];
    const isStreamingMessage =
      isStreaming &&
      messages.length > 0 &&
      lastMsg &&
      lastMsg.id === msg.id &&
      msg.role === "assistant";

    chatItems.push({
      type: "message",
      id: msg.id,
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

  async function handleSend(message: string, isDeepResearch?: boolean) {
    const store = useAssistantStore.getState();
    const sessionId = store.activeSessionId;
    const sessionEvents = sessionId ? (store.events.get(sessionId) ?? []) : [];
    const lastEvent = sessionEvents.length > 0 ? sessionEvents[sessionEvents.length - 1] : null;
    const isWaiting = lastEvent?.type === "wait";

    if (isDeepResearch) {
      await store.sendResearchMessage(message);
    } else if (isWaiting) {
      await store.sendResearchMessage(message);
    } else {
      await store.sendMessage(message);
    }
  }

  const handleStop = () => {
    const store = useAssistantStore.getState();
    store.stopStream();
  };

  if (!token) return null;

  // Determine if we should show the deep research right panel
  const showDeepResearchPanel = !!deepResearchState || !!pendingAction;

  return (
    <div className="relative flex h-full min-h-0">
      {/* Sidebar (Session List) */}
      <aside
        data-tour="assistant-sessions"
        className={`hidden xl:block h-full flex-shrink-0 bg-canvas border-r border-charcoal/20 transition-all duration-300 ${
          sidebarCollapsed ? "w-0 overflow-hidden border-r-0" : "w-64"
        }`}
      >
        {!sidebarCollapsed && (
          <div className="h-full w-full overflow-y-auto scrollbar-hide">
            <SessionList
              compact
              isCurrentSessionNew={isCurrentSessionNew}
              isCreating={isCreating}
              onClose={() => {}}
              onNewChat={handleNewChat}
              onSelectSession={() => {}}
            />
          </div>
        )}
      </aside>

      {/* Sidebar toggle button */}
      <button
        type="button"
        onClick={handleToggleSidebar}
        className="absolute left-0 top-1/2 -translate-y-1/2 z-10 hidden xl:flex items-center justify-center h-10 w-5 rounded-r-lg bg-surface-card border-y border-r border-charcoal/30 hover:bg-surface-hover hover:border-primary/50 text-charcoal shadow-[4px_0_12px_rgba(0,0,0,0.05)] transition-all duration-200"
        title={isCollapsed ? "Show sidebar" : "Hide sidebar"}
      >
        <ArrowsLeftRight size={14} weight="bold" />
      </button>

      <div className="flex min-w-0 flex-1 flex-col">

        {/* ── Empty state: greeting + chatbox centered ── */}
        {chatItems.length === 0 && !pendingAction ? (
          <div
            key={sessionId}
            className="relative flex flex-1 flex-col items-center justify-center mb-[8vh] animate-fade-in"
          >
            {/* Greeting */}
            <div className="px-4 w-full max-w-2xl">
              <ChatEmptyState />
            </div>

            {/* ChatBox with animated orange halo glow */}
            <div className="relative w-full max-w-2xl px-4 z-10">
              {/* Animated glow halo behind the chatbox */}
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-4 inset-y-0 -z-10 rounded-2xl animate-glow-pulse"
              />
              <ChatBox onSend={handleSend} onStop={handleStop} onNewChat={handleNewChat} />
            </div>

          </div>
        ) : (
          /* ── Normal chat layout ── */
          <>
            <div
              ref={containerRef}
              onScroll={handleScroll}
              className="min-h-0 flex-1 overflow-y-auto scroll-smooth px-3 py-4 pb-8 sm:px-4"
            >
              <div key={sessionId} className="relative animate-fade-in-up">
                <div className="mx-auto w-full max-w-4xl space-y-4">
                  {/* Project context banner */}
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

                  {/* Confirm Project Panel (Deep Research HITL) */}
                  <ConfirmProjectPanel />

                  {/* Thinking Panel */}
                  <ThinkingPanel events={sessionEvents} isStreaming={isStreaming} />
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
              className="shrink-0 border-t bg-canvas"
              style={{ borderColor: "var(--hairline)" }}
            >
              <div className="max-w-4xl mx-auto px-3 sm:px-4 py-3 sm:py-4">
                <ChatBox onSend={handleSend} onStop={handleStop} onNewChat={handleNewChat} />
              </div>
            </div>
          </>
        )}
      </div>

      {/* Deep Research Right Panel */}
      {showDeepResearchPanel && (
        <div className="hidden lg:block w-[420px] xl:w-[500px] h-full flex-shrink-0 border-l border-charcoal/20 bg-canvas overflow-y-auto">
          <div className="p-4 space-y-4">
            {/* Project Info Card */}
            {currentSession?.project_id && currentSession.project_title && (
              <div className="rounded-xl border border-primary/10 bg-gradient-to-br from-primary/5 to-surface-card p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Folder size={16} className="text-primary" weight="fill" />
                  <h3 className="font-ui text-sm font-semibold text-ink">Project Info</h3>
                </div>
                <p className="font-ui text-sm text-ink mb-1">{currentSession.project_title}</p>
                {deepResearchState && (
                  <div className="flex items-center gap-2 mt-2 text-xs text-charcoal/60">
                    <span className="px-2 py-0.5 rounded-full bg-surface-bone">
                      {deepResearchState.papersSaved} papers saved
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-surface-bone">
                      Stage: {deepResearchState.stage}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Deep Research Terminal */}
            <DeepResearchTerminal />
          </div>
        </div>
      )}
    </div>
  );
}

function getUserDisplayName(email: string | undefined): string {
  if (!email) return "You";
  return email.split("@")[0] || "You";
}
