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
import { useAssistantStore, useMessages } from "@/lib/stores/assistant-store";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useUIStore } from "@/lib/stores/ui-store";
import { ChatMessage, GroupedThoughts } from "@/components/assistant";
import { ChatBox } from "@/components/assistant/ChatBox";
import { ToolPanel } from "@/components/assistant/ToolPanel";

import { SessionList } from "@/components/assistant/SessionList";
import { ProjectSelector } from "@/components/ProjectSelector";
import { useProjectsStore } from "@/lib/stores/projects-store";
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
  const currentSession = useAssistantStore((s) => s.currentSession);

  // Tool panel state lives in the global UI store
  const toolPanelOpen = useUIStore((s) => s.assistantToolPanelOpen);
  const setToolPanelOpen = useUIStore((s) => s.setAssistantToolPanelOpen);

  // Sessions left panel state (synced with header trigger)
  const sessionsOpen = useUIStore((s) => s.assistantSessionsOpen);
  const setSessionsOpen = useUIStore((s) => s.setAssistantSessionsOpen);

  const projects = useProjectsStore((s) => s.projects);
  const fetchProjects = useProjectsStore((s) => s.fetchProjects);
  const updateSessionProject = useAssistantStore((s) => s.updateSessionProject);

  const [jumpToLatest, setJumpToLatest] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Load sessions and projects
  useEffect(() => {
    if (!token) return;
    void loadSessions();
    void fetchProjects();
  }, [token, loadSessions, fetchProjects]);

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

  // Pre-compute thought accumulation map once (O(n) instead of O(n²) per render)
  const thoughtMap = buildThoughtAccumulationMap(sessionEvents);

  // Deduplicate thought events by iteration index to render exactly one thought card per cycle per user message turn
  const seenThoughtIterations = new Set<number>();
  const visibleEvents = sessionEvents.filter((event) => {
    if (!event || !event.id || !event.type) {
      return false;
    }
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

  // Build chat items from messages (stable, no array index keys)
  const chatItems: (
    | {
        type: "message";
        id: string;
        message: MessageEvent;
        isStreaming: boolean;
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

  // Then, add grouped thoughts from events (for activity display)
  // Group by iteration - each iteration gets ONE thought with accumulated content
  const thoughtsByIteration = new Map<number, { id: string; iteration: number; content: string; isStreaming: boolean }>();
  let lastThoughtEvent: ThoughtEvent | null = null;
  for (const event of sessionEvents) {
    if (!event || !event.id) {
      continue;
    }
    if (event.type === "thought") {
      const lastEv = sessionEvents[sessionEvents.length - 1];
      const isLastEvent = sessionEvents.length > 0 && lastEv && lastEv.id === event.id;
      const content = getAccumulatedThought(event as ThoughtEvent, sessionEvents, thoughtMap);

      // Always update with the latest accumulated content for this iteration
      thoughtsByIteration.set(event.iteration, {
        id: event.id,
        iteration: event.iteration,
        content,
        isStreaming: isLastEvent && isStreaming,
      });
      lastThoughtEvent = event;
    }
  }

  // Convert to sorted array
  const sortedThoughts = Array.from(thoughtsByIteration.values()).sort(
    (a, b) => a.iteration - b.iteration
  );

  if (sortedThoughts.length > 0 && lastThoughtEvent) {
    chatItems.push({
      type: "grouped-thoughts",
      id: `group-${lastThoughtEvent.id}`,
      thoughts: sortedThoughts,
      isStreaming: sortedThoughts.some((t) => t.isStreaming),
    });
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
                {/* Project Selector Header */}
                {currentSession && (
                  <div className="flex justify-center mb-6 pt-4">
                    <div className="w-full max-w-sm">
                      <ProjectSelector
                        projects={projects}
                        selectedId={currentSession.project_id || ""}
                        onChange={(id) => updateSessionProject(currentSession.id, id)}
                        label=""
                        placeholder="Link to a project to provide context..."
                        showStatus={false}
                      />
                    </div>
                  </div>
                )}

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
                {chatItems.map((item, index) => {
                  const isLastAssistantMessage = 
                    item.type === "message" && 
                    item.message.role === "assistant" && 
                    item.id === chatItems.slice().reverse().find(i => i.type === "message" && i.message.role === "assistant")?.id;

                  return item.type === "grouped-thoughts" ? (
                    <GroupedThoughts
                      key={item.id}
                      thoughts={item.thoughts}
                      isStreaming={item.isStreaming}
                    />
                  ) : (
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

                <div ref={messagesEndRef} />
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
