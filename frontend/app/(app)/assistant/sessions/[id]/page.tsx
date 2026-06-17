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
import { useParams } from "next/navigation";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useUIStore } from "@/lib/stores/ui-store";
import { ChatMessage } from "@/components/assistant/ChatMessage";
import { ChatBox } from "@/components/assistant/ChatBox";
import { ToolPanel } from "@/components/assistant/ToolPanel";
import type {
  AssistantEventData,
  DoneEvent,
  ErrorEvent,
  PlanData,
  StepEvent,
  ToolEvent,
} from "@/lib/types/assistant";
import {
  ArrowClockwise,
  CaretDown,
  CheckCircle,
  Circle,
  Gear,
  Lightning,
  PaperPlaneTilt,
  Pulse,
  Spinner,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";

export default function AssistantSessionPage() {
  const params = useParams();
  const sessionId = params.id as string;

  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const selectSession = useAssistantStore((s) => s.selectSession);
  const activeSessionId = useAssistantStore((s) => s.activeSessionId);
  const isStreaming = useAssistantStore((s) => s.isStreaming);
  const loadSessions = useAssistantStore((s) => s.loadSessions);
  const events = useAssistantStore((s) => s.events);
  const currentPlan = useAssistantStore((s) => s.currentPlan);

  // Tool panel state lives in the global UI store so the header button
  // (rendered inside AppShell) and the panel itself stay in sync.
  const toolPanelOpen = useUIStore((s) => s.assistantToolPanelOpen);
  const setToolPanelOpen = useUIStore((s) => s.setAssistantToolPanelOpen);

  const [jumpToLatest, setJumpToLatest] = useState(false);
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
      // Auto-scroll for user messages and assistant completions
      if (lastEvent.type === "message" || lastEvent.type === "done") {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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
  const visibleEvents = sessionEvents.filter((event) =>
    (event.type === "message" && !isTechnicalMessage(event)) ||
    event.type === "error"
  );
  const activityEvents = sessionEvents.filter((event) =>
    event.type !== "message" && event.type !== "error" && event.type !== "title"
  );

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
                {visibleEvents.length === 0 && (
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
                {visibleEvents.map((event) =>
                  event.type === "error" ? (
                    <ErrorMessage
                      key={event.id}
                      event={event as ErrorEvent}
                    />
                  ) : (
                    <ChatMessage
                      key={event.id}
                      event={event}
                      userName={userName}
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
            {activityEvents.length > 0 && (
              <>
                <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-80 xl:block">
                  <div className="sticky top-4 mr-4 pointer-events-auto">
                    <ActivityPanel
                      events={activityEvents}
                      plan={currentPlan}
                    />
                  </div>
                </div>
                <div className="mt-6 xl:hidden">
                  <ActivityPanel
                    events={activityEvents}
                    plan={currentPlan}
                  />
                </div>
              </>
            )}

            {/* Jump to latest button */}
            {jumpToLatest && (
              <div className="sticky bottom-3 z-10 flex justify-center">
                <button
                  type="button"
                  onClick={() => {
                    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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

function ActivityPanel({
  events,
  plan,
}: {
  events: AssistantEventData[];
  plan: PlanData | null;
}) {
  const completedSteps = plan?.steps.filter((step) => step.status === "completed").length ?? 0;
  const totalSteps = plan?.steps.length ?? 0;
  const toolCount = events.filter((event) => event.type === "tool").length;
  const lastActivity = getActivityLabel(events[events.length - 1], plan);
  const hasRunning = events.some(
    (event) =>
      event.type === "step" && (event as StepEvent).status === "running"
  );

  return (
    <aside
      className="animate-slide-in-right overflow-hidden rounded-2xl border border-charcoal/10 bg-canvas shadow-sm"
      aria-label="Workflow activity"
    >
      <ActivityHeader
        completedSteps={completedSteps}
        totalSteps={totalSteps}
        toolCount={toolCount}
        lastActivity={lastActivity}
        hasRunning={hasRunning}
      />

      <div className="border-t border-charcoal/10 px-4 py-3">
        {plan && <PlanSection plan={plan} />}
        {events.length > 0 && <EventList events={events} />}
      </div>
    </aside>
  );
}

function ActivityHeader({
  completedSteps,
  totalSteps,
  toolCount,
  lastActivity,
  hasRunning,
}: {
  completedSteps: number;
  totalSteps: number;
  toolCount: number;
  lastActivity: string | null;
  hasRunning: boolean;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const progress =
    totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0;

  return (
    <button
      type="button"
      onClick={() => setCollapsed((c) => !c)}
      className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-bone/50"
      aria-expanded={!collapsed}
    >
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
          hasRunning ? "bg-primary/10" : "bg-surface-bone"
        }`}
      >
        {hasRunning ? (
          <Pulse size={16} weight="fill" className="text-primary animate-pulse" />
        ) : (
          <Lightning size={16} weight="fill" className="text-primary" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="font-ui text-sm font-semibold text-ink">Activity</p>
          {totalSteps > 0 && (
            <span className="font-ui text-[11px] font-medium text-charcoal/60">
              {completedSteps}/{totalSteps}
            </span>
          )}
          {toolCount > 0 && (
            <span className="font-ui text-[11px] font-medium text-charcoal/60">
              · {toolCount} tools
            </span>
          )}
        </div>
        {lastActivity && (
          <p className="mt-0.5 truncate font-ui text-[11px] text-charcoal/60">
            {lastActivity}
          </p>
        )}
        {totalSteps > 0 && (
          <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-surface-bone">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>

      <CaretDown
        size={14}
        weight="bold"
        className={`shrink-0 text-charcoal/60 transition-transform duration-300 ${
          collapsed ? "" : "rotate-180"
        }`}
      />
    </button>
  );
}

function PlanSection({ plan }: { plan: PlanData }) {
  return (
    <div className="mb-3">
      <p className="mb-2 font-ui text-[10px] font-semibold uppercase tracking-wider text-charcoal/50">
        {plan.title || "Plan"}
      </p>
      <ol className="space-y-1.5">
        {plan.steps.map((step, idx) => (
          <li
            key={step.id}
            className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-surface-bone/50 animate-fade-in"
            style={{ animationDelay: `${idx * 40}ms` }}
          >
            <ActivityStatusIcon status={step.status} />
            <p className="font-ui text-xs leading-relaxed text-ink">
              {step.description}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function EventList({ events }: { events: AssistantEventData[] }) {
  const recent = events.slice(-6);
  return (
    <div>
      <p className="mb-2 font-ui text-[10px] font-semibold uppercase tracking-wider text-charcoal/50">
        Recent
      </p>
      <ul className="space-y-1">
        {recent.map((event, idx) => (
          <li
            key={event.id}
            className="animate-fade-in"
            style={{ animationDelay: `${idx * 30}ms` }}
          >
            <ActivityEvent event={event} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ActivityEvent({ event }: { event: AssistantEventData }) {
  if (event.type === "step") {
    const step = event as StepEvent;
    return (
      <div className="flex items-start gap-2 rounded-md px-2 py-1 font-ui text-[11px] text-charcoal transition-colors hover:bg-surface-bone/40">
        <ActivityStatusIcon status={step.status} small />
        <span className="leading-relaxed">{step.description}</span>
      </div>
    );
  }

  if (event.type === "tool") {
    const tool = event as ToolEvent;
    const isRunning = tool.status === "calling";
    return (
      <div
        className={`flex items-start gap-2 rounded-md px-2 py-1 font-ui text-[11px] transition-colors ${
          isRunning
            ? "bg-primary/5 text-ink"
            : "text-charcoal hover:bg-surface-bone/40"
        }`}
      >
        <Gear
          size={11}
          weight={isRunning ? "fill" : "regular"}
          className={`mt-0.5 shrink-0 text-primary ${
            isRunning ? "animate-spin" : ""
          }`}
        />
        <span className="leading-relaxed">
          <span className="font-medium">{tool.function}</span>
          <span className="ml-1 text-charcoal/50">· {tool.status}</span>
        </span>
      </div>
    );
  }

  if (event.type === "done") {
    const done = event as DoneEvent;
    return (
      <div className="flex items-start gap-2 rounded-md px-2 py-1 font-ui text-[11px] text-charcoal/70 transition-colors hover:bg-surface-bone/40">
        <CheckCircle
          size={11}
          className="mt-0.5 shrink-0 text-green-500"
          weight="fill"
        />
        <span className="leading-relaxed">{done.summary || "Completed"}</span>
      </div>
    );
  }

  return null;
}

function ActivityStatusIcon({
  status,
  small,
}: {
  status: StepEvent["status"];
  small?: boolean;
}) {
  const size = small ? 11 : 14;
  if (status === "running") {
    return (
      <Spinner
        size={size}
        weight="bold"
        className="mt-0.5 shrink-0 animate-spin text-primary"
      />
    );
  }
  if (status === "completed") {
    return (
      <CheckCircle
        size={size}
        weight="fill"
        className="mt-0.5 shrink-0 text-green-500"
      />
    );
  }
  if (status === "failed") {
    return (
      <XCircle
        size={size}
        weight="fill"
        className="mt-0.5 shrink-0 text-red-500"
      />
    );
  }
  return (
    <Circle
      size={size}
      weight="regular"
      className="mt-0.5 shrink-0 text-charcoal/30"
    />
  );
}

function getActivityLabel(
  event: AssistantEventData | undefined,
  plan: PlanData | null
): string | null {
  if (!event) {
    return plan?.title ?? null;
  }
  if (event.type === "step") {
    return (event as StepEvent).description;
  }
  if (event.type === "tool") {
    const tool = event as ToolEvent;
    return `${tool.function} · ${tool.status}`;
  }
  if (event.type === "done") {
    return (event as DoneEvent).summary ?? "Completed";
  }
  if (event.type === "plan") {
    return "Plan updated";
  }
  return null;
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
