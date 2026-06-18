/**
 * Assistant session chat page.
 *
 * Layout:
 * - Center: chat stream + chat input
 * - Right: tool panel (slide-in / drawer), toggled from the AppShell header
 *
 * The session list, "New chat" button and "View tool" toggle all live in
 * the AppShell header (see <AssistantHeaderControls />). This page only
 * renders the chat surface and the right-hand tool panel.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useUIStore } from "@/lib/stores/ui-store";
import { ChatMessage, GroupedThoughts } from "@/components/assistant";
import { ChatBox } from "@/components/assistant/ChatBox";
import { ToolPanel } from "@/components/assistant/ToolPanel";
import { IterationPanel } from "@/components/assistant/IterationPanel";
import { SessionList } from "@/components/assistant/SessionList";
import type {
  AssistantEventData,
  ErrorEvent,
  MessageEvent,
  ThoughtEvent,
} from "@/lib/types/assistant";
import {
  ArrowClockwise,
  PaperPlaneTilt,
  WarningCircle,
  CaretLeft,
  CaretRight,
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
  const currentPhase = useAssistantStore((s) => s._currentPhase);

  // Tool panel state lives in the global UI store
  const toolPanelOpen = useUIStore((s) => s.assistantToolPanelOpen);
  const setToolPanelOpen = useUIStore((s) => s.setAssistantToolPanelOpen);

  // Sessions left panel state (synced with header trigger)
  const sessionsOpen = useUIStore((s) => s.assistantSessionsOpen);
  const setSessionsOpen = useUIStore((s) => s.setAssistantSessionsOpen);

  const [jumpToLatest, setJumpToLatest] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Load sessions and select this one
  useEffect(() => {
    if (!token) return;
    void loadSessions();
  }, [token, loadSessions]);

  useEffect(() => {
    if (!sessionId || sessionId === activeSessionId) return;
    void selectSession(sessionId);
  }, [sessionId, activeSessionId, selectSession]);

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

  // Get events for current session
  const sessionEvents = sessionId ? (events.get(sessionId) ?? []) : [];
  const userName = getUserDisplayName(user?.email);

  // Pre-compute thought accumulation map once (O(n) instead of O(n²) per render)
  const thoughtMap = buildThoughtAccumulationMap(sessionEvents);

  // Deduplicate thought events by iteration index to render exactly one thought card per cycle per user message turn
  const seenThoughtIterations = new Set<number>();
  const visibleEvents = sessionEvents.filter((event) => {
    if (event.type === "message" && (event as any).role === "user") {
      // User message starts a new turn, reset the seen iterations tracker
      seenThoughtIterations.clear();
      return true;
    }
    if (event.type === "thought") {
      const iteration = (event as any).iteration;
      if (seenThoughtIterations.has(iteration)) {
        return false;
      }
      seenThoughtIterations.add(iteration);
      return true;
    }
    return (
      (event.type === "message" && !isTechnicalMessage(event)) ||
      event.type === "error"
    );
  });

  // Group contiguous thoughts into a single element
  const chatItems: (
    | {
        type: "event";
        id: string;
        event: AssistantEventData;
      }
    | {
        type: "grouped-thoughts";
        id: string;
        thoughts: {
          id: string;
          iteration: number;
          content: string;
          isStreaming: boolean;
        }[];
        isStreaming: boolean;
      }
  )[] = [];

  let currentThoughtsGroup: {
    type: "grouped-thoughts";
    id: string;
    thoughts: {
      id: string;
      iteration: number;
      content: string;
      isStreaming: boolean;
    }[];
    isStreaming: boolean;
  } | null = null;

  for (const event of visibleEvents) {
    if (event.type === "thought") {
      const isLastEvent = sessionEvents.length > 0 && sessionEvents[sessionEvents.length - 1].id === event.id;
      const content = getAccumulatedThought(event as ThoughtEvent, sessionEvents, thoughtMap);

      if (!currentThoughtsGroup) {
        currentThoughtsGroup = {
          type: "grouped-thoughts",
          id: `group-${event.id}`,
          thoughts: [],
          isStreaming: false,
        };
      }

      currentThoughtsGroup.thoughts.push({
        id: event.id,
        iteration: event.iteration,
        content,
        isStreaming: isLastEvent && isStreaming,
      });

      if (isLastEvent && isStreaming) {
        currentThoughtsGroup.isStreaming = true;
      }
    } else {
      if (currentThoughtsGroup) {
        chatItems.push(currentThoughtsGroup);
        currentThoughtsGroup = null;
      }
      chatItems.push({
        type: "event",
        id: event.id,
        event,
      });
    }
  }

  if (currentThoughtsGroup) {
    chatItems.push(currentThoughtsGroup);
  }

  const activityEvents = sessionEvents.filter((event) =>
    event.type === "tool" || event.type === "done" || event.type === "wait" || event.type === "iteration"
  );

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
        className={`hidden xl:block transition-all duration-300 overflow-hidden flex-shrink-0 bg-canvas border-r ${
          sessionsOpen ? "w-64" : "w-0"
        }`}
        style={{ borderColor: "var(--hairline)" }}
      >
        <div className="h-full w-64 overflow-y-auto">
          <SessionList
            compact
            isCurrentSessionNew={isCurrentSessionNew}
            isCreating={isCreating}
            onClose={() => setSessionsOpen(false)}
            onNewChat={handleNewChat}
            onSelectSession={() => {}}
          />
        </div>
      </aside>

      {/* Sidebar Toggle Button (desktop only) */}
      <button
        type="button"
        onClick={() => setSessionsOpen(!sessionsOpen)}
        className="hidden xl:flex absolute top-4 z-20 h-9 w-9 items-center justify-center rounded-lg border bg-canvas text-charcoal shadow-sm hover:text-ink hover:bg-surface-bone transition-all duration-300 active:scale-95"
        style={{
          left: sessionsOpen ? "272px" : "16px",
          borderColor: "var(--hairline)",
        }}
        title={sessionsOpen ? "Collapse sidebar" : "Expand sidebar"}
      >
        {sessionsOpen ? (
          <CaretLeft size={16} weight="bold" />
        ) : (
          <CaretRight size={16} weight="bold" />
        )}
      </button>

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
          className="min-h-0 flex-1 overflow-y-auto px-3 py-4 pb-8 sm:px-4"
        >
          <div className="relative">
            {/* Chat column - centered in the viewport, full width up to
                3xl breakpoint. */}
            <div className="mx-auto w-full max-w-4xl space-y-4">
                {/* Welcome message if no events */}
                {chatItems.length === 0 && (
                  <div className="text-center py-12">
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
                {chatItems.map((item) =>
                  item.type === "grouped-thoughts" ? (
                    <GroupedThoughts
                      key={item.id}
                      thoughts={item.thoughts}
                      isStreaming={item.isStreaming}
                    />
                  ) : item.event.type === "error" ? (
                    <ErrorMessage
                      key={item.id}
                      event={item.event as ErrorEvent}
                    />
                  ) : (
                    <ChatMessage
                      key={item.id}
                      event={item.event}
                      userName={userName}
                      allEvents={sessionEvents}
                    />
                  )
                )}

                {/* Streaming indicator */}
                {isStreaming && (
                  <div className="flex items-center gap-2 text-charcoal font-ui text-sm py-2">
                    <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
                    Thinking...
                  </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Activity panel - absolutely positioned in the right
                whitespace (xl+), inline below on smaller viewports. */}
            {(activityEvents.length > 0 || currentPhase !== null) && (
              <>
                <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-80 xl:block">
                  <div className="sticky top-4 mr-4 pointer-events-auto">
                    <IterationPanel title="Agent Progress" />
                  </div>
                </div>
                <div className="mt-6 xl:hidden">
                  <IterationPanel title="Agent Progress" />
                </div>
              </>
            )}

            {/* Jump to latest button */}
            {jumpToLatest && (
              <div className="sticky bottom-3 z-10 flex justify-center">
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
            <ChatBox onSend={handleSend} onStop={handleStop} />
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

function isTechnicalMessage(event: AssistantEventData): boolean {
  if (event.type !== "message") {
    return false;
  }

  const content = event.content.trim();
  if (event.role !== "assistant") {
    return false;
  }

  // Filter out internal step/plan progress chatter that the agent
  // emits as message events but is already reflected in the Activity
  // panel. Keeping them in the chat stream just clutters the UI.
  return (
    content.startsWith("Analyzing request about") ||
    content.startsWith("Breaking down the task into actionable steps") ||
    content.startsWith("Plan already complete.") ||
    content.startsWith("Flow completed.") ||
    content.startsWith("Step '") ||
    content.startsWith("Plan continues") ||
    content.startsWith("Plan needs updating") ||
    content.startsWith("Checking if plan needs updates")
  );
}













function ErrorMessage({ event }: { event: ErrorEvent }) {
  return (
    <div className="animate-fade-in-up overflow-hidden rounded-2xl border border-red-200/80 bg-gradient-to-br from-red-50 via-red-50 to-orange-50 shadow-sm">
      <div className="flex items-start gap-3 p-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-red-100">
          <WarningCircle
            size={20}
            weight="fill"
            className="text-red-600"
          />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-ui text-sm font-semibold text-red-700">
            {event.code === "CHAT_FAILED"
              ? "Chat failed"
              : event.code}
          </p>
          <p className="mt-1 font-ui text-[13px] leading-relaxed text-red-600/90">
            {event.message}
          </p>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-1.5 rounded-full bg-red-600 px-3 py-1.5 font-ui text-xs font-medium text-white transition-all duration-200 hover:bg-red-700 active:scale-95"
            >
              <ArrowClockwise size={12} weight="bold" />
              Retry
            </button>
            <span className="font-ui text-[11px] text-red-500/70">
              Try sending your message again
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function getAccumulatedThought(
  event: ThoughtEvent,
  allEvents: AssistantEventData[],
  thoughtMap: Map<string, string> // Pre-computed thought accumulation map
): string {
  // Use pre-computed accumulation map for O(1) lookup instead of O(n) scan
  return thoughtMap.get(event.id) ?? event.delta ?? "";
}

/**
 * Pre-compute thought accumulation map for O(1) getAccumulatedThought calls.
 * Builds: event.id -> accumulated thought text for that event's iteration
 */
function buildThoughtAccumulationMap(
  allEvents: AssistantEventData[]
): Map<string, string> {
  const thoughtMap = new Map<string, string>();
  let lastUserMsgIndex = 0;
  const thoughtBuffers = new Map<number, string>(); // iteration -> accumulated text

  for (let i = 0; i < allEvents.length; i++) {
    const e = allEvents[i];

    // Track user message boundaries to reset thought buffers
    if (e.type === "message" && (e as MessageEvent).role === "user") {
      lastUserMsgIndex = i;
      thoughtBuffers.clear();
    }

    if (e.type === "thought") {
      const thought = e as ThoughtEvent;
      const iter = thought.iteration;

      // Update buffer for this iteration
      const currentBuffer = thoughtBuffers.get(iter) ?? "";
      thoughtBuffers.set(iter, currentBuffer + (thought.delta ?? ""));

      // Store the accumulated result keyed by this event's ID
      thoughtMap.set(e.id, thoughtBuffers.get(iter) ?? "");
    }
  }

  return thoughtMap;
}
