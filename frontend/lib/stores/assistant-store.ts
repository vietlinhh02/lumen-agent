/**
 * Zustand store for the Assistant (Plan-Act Chat).
 * 
 * Manages:
 * - Session list and selection
 * - SSE event stream handling
 * - Plan state
 * - Tool artifact previews
 * - Streaming state
 */

"use client";

import { create } from "zustand";
import { useAuthStore } from "./auth-store";
import * as api from "@/lib/api/assistant";
import type {
  AssistantState,
  AssistantEventData,
  SessionCreate,
  SessionResponse,
  SessionSummary,
  ToolArtifact,
  MessageEvent,
  TitleEvent,
  PlanEvent,
  StepEvent,
  ToolEvent,
  DoneEvent,
  ErrorEvent,
  WaitEvent,
  ChatResult,
} from "@/lib/types/assistant";

interface ExtendedAssistantState extends AssistantState {
  /** Internal: current chat result for cancellation */
  _chatResult?: ChatResult;
  /** Internal: apply an event to a specific session. */
  _applyEventToSession: (sessionId: string, event: AssistantEventData) => void;
  /** Internal: extract tool artifact from result */
  _extractToolArtifact: (event: ToolEvent) => void;
}

function normalizePersistedEvent(
  eventType: string,
  payload: Record<string, unknown>,
  id: string,
  timestamp: string
): AssistantEventData {
  return {
    ...payload,
    type: payload.type ?? eventType,
    id,
    timestamp,
  } as AssistantEventData;
}

export const useAssistantStore = create<ExtendedAssistantState>()((set, get) => ({
  // ── Initial State ──────────────────────────────────────────────────────────

  sessions: [],
  loadingSessions: false,
  activeSessionId: null,
  currentSession: null,
  loadingSession: false,
  events: new Map(),
  isStreaming: false,
  currentPlan: null,
  currentToolArtifact: null,
  error: null,

  // ── Session Actions ─────────────────────────────────────────────────────────

  /**
   * Load the sessions list. Deduplicates concurrent calls.
   */
  async loadSessions(force = false) {
    const token = useAuthStore.getState().token;
    if (!token) return;

    const state = get();

    // Skip if loading or cache is fresh (unless force)
    if (!force && state.loadingSessions) {
      return;
    }

    set({ loadingSessions: true, error: null });

    try {
      const response = await api.listSessions();
      set({
        sessions: response.sessions,
        loadingSessions: false,
      });
    } catch (err) {
      set({
        loadingSessions: false,
        error: err instanceof Error ? err.message : "Failed to load sessions",
      });
    }
  },

  /**
   * Rename a session. Persists to backend and updates local list.
   */
  async renameSession(sessionId: string, title: string) {
    const trimmed = title.trim();
    if (!trimmed) return;

    // Optimistic local update so the list reflects the new title immediately.
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId ? { ...s, title: trimmed } : s
      ),
      currentSession:
        state.currentSession?.id === sessionId
          ? { ...state.currentSession, title: trimmed }
          : state.currentSession,
    }));

    try {
      await api.updateSessionTitle(sessionId, trimmed);
    } catch (err) {
      // Revert on failure by refetching the canonical list.
      void get().loadSessions(true);
      set({
        error: err instanceof Error ? err.message : "Failed to rename session",
      });
    }
  },

  /**
   * Create a new assistant session.
   */
  async createSession(data?: SessionCreate): Promise<SessionResponse | null> {
    const token = useAuthStore.getState().token;
    if (!token) return null;

    try {
      const session = await api.createSession(data);
      
      // Add to sessions list
      const newSummary: SessionSummary = {
        id: session.id,
        title: session.title,
        project_id: session.project_id,
        project_title: null,
        status: session.status as SessionSummary["status"],
        created_at: session.created_at,
        updated_at: session.created_at,
        event_count: 0,
      };
      
      set((state) => ({
        sessions: [newSummary, ...state.sessions],
        activeSessionId: session.id,
      }));

      return session;
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to create session",
      });
      return null;
    }
  },

  /**
   * Select a session and load its details + replay events.
   */
  async selectSession(id: string) {
    const token = useAuthStore.getState().token;
    if (!token) return;

    // Already selected?
    if (get().activeSessionId === id && get().currentSession) {
      return;
    }

    set({ loadingSession: true, error: null, activeSessionId: id });

    try {
      // Fetch session detail (includes events for replay)
      const detail = await api.getSession(id);

      // Build events map
      const eventsMap = new Map<string, AssistantEventData[]>();
      const sessionEvents = detail.events.map((event) =>
        normalizePersistedEvent(
          event.event_type,
          event.payload,
          event.id,
          event.created_at
        )
      );
      eventsMap.set(id, sessionEvents);

      set({
        currentSession: detail,
        events: eventsMap,
        currentPlan: detail.plan,
        loadingSession: false,
      });
    } catch (err) {
      set({
        loadingSession: false,
        activeSessionId: null,
        error: err instanceof Error ? err.message : "Failed to load session",
      });
    }
  },

  /**
   * Delete a session.
   */
  async deleteSession(id: string): Promise<boolean> {
    try {
      await api.deleteSession(id);
      set((state) => ({
        sessions: state.sessions.filter((s) => s.id !== id),
        activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
        currentSession: state.currentSession?.id === id ? null : state.currentSession,
      }));
      return true;
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to delete session",
      });
      return false;
    }
  },

  // ── Chat Actions ────────────────────────────────────────────────────────────

  /**
   * Send a message and stream events.
   */
  async sendMessage(message: string) {
    const state = get();
    const sessionId = state.activeSessionId;

    if (!sessionId) {
      set({ error: "No active session. Create or select a session first." });
      return;
    }

    // Add user message to events immediately
    const userMessageEvent: MessageEvent = {
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      type: "message",
      role: "user",
      content: message,
    };

    set((state) => {
      const eventsMap = new Map(state.events);
      const sessionEvents = [...(eventsMap.get(sessionId) ?? []), userMessageEvent];
      eventsMap.set(sessionId, sessionEvents);
      return {
        events: eventsMap,
        isStreaming: true,
        error: null,
        currentToolArtifact: null,
      };
    });

    // Start SSE stream
    const chatResult = api.chat(sessionId, message, {
      onMessage: (event: MessageEvent) => {
        get()._applyEventToSession(sessionId, event);
      },
      onTitle: (event: TitleEvent) => {
        get()._applyEventToSession(sessionId, event);
        // Update session title in list
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === sessionId ? { ...s, title: event.title } : s
          ),
        }));
      },
      onPlan: (event: PlanEvent) => {
        get()._applyEventToSession(sessionId, event);
      },
      onStep: (event: StepEvent) => {
        get()._applyEventToSession(sessionId, event);
      },
      onTool: (event: ToolEvent) => {
        get()._applyEventToSession(sessionId, event);
        // Extract tool artifact for preview
        if (event.status === "called" && event.result) {
          get()._extractToolArtifact(event);
        }
      },
      onDone: (event: DoneEvent) => {
        get()._applyEventToSession(sessionId, event);
        set({ isStreaming: false });
      },
      onError: (event: ErrorEvent) => {
        get()._applyEventToSession(sessionId, event);
        set({ isStreaming: false, error: event.message });
      },
      onWait: (event: WaitEvent) => {
        get()._applyEventToSession(sessionId, event);
        set({ isStreaming: false });
      },
    });

    // Handle stream completion
    chatResult.finished
      .catch((err) => {
        if (err instanceof Error && err.name !== "AbortError") {
          set({
            isStreaming: false,
            error: err.message,
          });
        }
      })
      .finally(() => {
        set({ isStreaming: false });
      });

    // Store cancel function for stopStream
    set({ _chatResult: chatResult });
  },

  /**
   * Stop the current stream.
   */
  stopStream() {
    const chatResult = get()._chatResult;

    if (chatResult) {
      chatResult.cancel();
      
      // Call stopSession on backend
      const sessionId = get().activeSessionId;
      if (sessionId) {
        api.stopSession(sessionId).catch(() => {
          // Ignore backend errors - stream is already cancelled
        });
      }
    }

    set({ isStreaming: false });
  },

  // ── Event Processing ───────────────────────────────────────────────────────

  /**
   * Apply an event to the store state.
   * Handles all event types and updates the appropriate state.
   */
  applyEvent(event: AssistantEventData) {
    const sessionId = get().activeSessionId;
    if (!sessionId) return;

    get()._applyEventToSession(sessionId, event);
  },

  _applyEventToSession(sessionId: string, event: AssistantEventData) {
    set((state) => {
      const eventsMap = new Map(state.events);
      const sessionEvents = [...(eventsMap.get(sessionId) ?? [])];
      
      // Avoid duplicates by ID
      if (!sessionEvents.some((e) => e.id === event.id)) {
        sessionEvents.push(event);
        eventsMap.set(sessionId, sessionEvents);
      }

      // Update plan if this is a plan event
      let currentPlan = state.currentPlan;
      if (event.type === "plan") {
        const planEvent = event as PlanEvent;
        currentPlan = {
          id: planEvent.plan_id,
          title: planEvent.title,
          language: planEvent.language,
          steps: planEvent.steps,
          current_step_index: 0,
          status: "in_progress",
          created_at: planEvent.timestamp,
          updated_at: planEvent.timestamp,
        };
      } else if (event.type === "step" && currentPlan) {
        // Update step status in plan
        const stepEvent = event as StepEvent;
        currentPlan = {
          ...currentPlan,
          steps: currentPlan.steps.map((step) =>
            step.id === stepEvent.step_id
              ? { ...step, status: stepEvent.status }
              : step
          ),
          current_step_index:
            stepEvent.status === "completed"
              ? currentPlan.current_step_index + 1
              : currentPlan.current_step_index,
        };
      }

      // Update session status in list
      let sessions = state.sessions;
      if (event.type === "done" || event.type === "error") {
        const newStatus = event.type === "done" ? "completed" : "failed";
        sessions = state.sessions.map((s) =>
          s.id === sessionId ? { ...s, status: newStatus as SessionSummary["status"] } : s
        );
      }

      return {
        events: eventsMap,
        currentPlan,
        sessions,
      };
    });
  },

  /**
   * Clear unread indicators for a session.
   * @deprecated - Reserved for future read indicators implementation
   */
  clearUnread(sessionId: string) {
    void sessionId;
    // Intentionally unused - reserved for future read indicators
  },

  // ── Internal Helpers ───────────────────────────────────────────────────────

  /**
   * Extract tool artifact from a completed tool call result.
   * This populates the ToolPanel preview.
   */
  _extractToolArtifact(event: ToolEvent) {
    const result = event.result as Record<string, unknown> | null;
    if (!result) return;

    let artifact: ToolArtifact | null = null;

    // Check for tool-specific result patterns
    if (event.function === "list_projects" && Array.isArray(result)) {
      artifact = {
        type: "project",
        title: "Projects",
        data: result,
      };
    } else if (event.function === "search_papers" && result.papers) {
      artifact = {
        type: "papers",
        title: "Search Results",
        data: result.papers,
      };
    } else if (event.function === "list_project_papers" && Array.isArray(result)) {
      artifact = {
        type: "papers",
        title: "Saved Papers",
        data: result,
      };
    } else if (event.function === "list_matrix_rows" && Array.isArray(result)) {
      artifact = {
        type: "matrix",
        title: "Literature Matrix",
        data: result,
      };
    } else if (event.function === "list_gaps" && Array.isArray(result)) {
      artifact = {
        type: "gaps",
        title: "Research Gaps",
        data: result,
      };
    } else if (event.function === "list_conflicts" && Array.isArray(result)) {
      artifact = {
        type: "conflicts",
        title: "Conflicting Findings",
        data: result,
      };
    } else if (event.function === "get_report" && result.content_markdown) {
      artifact = {
        type: "report",
        title: (result.title as string) || "Report",
        data: result,
        reportId: result.id as string,
      };
    } else if (event.function === "retrieve_evidence" && Array.isArray(result.chunks || result)) {
      artifact = {
        type: "evidence",
        title: "Evidence Chunks",
        data: result.chunks || result,
      };
    }

    if (artifact) {
      set({ currentToolArtifact: artifact });
    }
  },

  // ── Reset ──────────────────────────────────────────────────────────────────

  reset() {
    set({
      sessions: [],
      loadingSessions: false,
      activeSessionId: null,
      currentSession: null,
      loadingSession: false,
      events: new Map(),
      isStreaming: false,
      currentPlan: null,
      currentToolArtifact: null,
      error: null,
      _chatResult: undefined,
    });
  },
}));

// ── Convenience Hooks ──────────────────────────────────────────────────────────

/**
 * Hook to get events for the active session.
 */
export function useAssistantEvents(): AssistantEventData[] {
  const sessionId = useAssistantStore((s) => s.activeSessionId);
  const eventsMap = useAssistantStore((s) => s.events);
  
  if (!sessionId) return [];
  return eventsMap.get(sessionId) ?? [];
}

/**
 * Hook to get the current plan.
 */
export function useCurrentPlan() {
  return useAssistantStore((s) => s.currentPlan);
}

/**
 * Hook to get the current tool artifact.
 */
export function useCurrentToolArtifact() {
  return useAssistantStore((s) => s.currentToolArtifact);
}

/**
 * Hook to check if streaming.
 */
export function useIsStreaming(): boolean {
  return useAssistantStore((s) => s.isStreaming);
}

/**
 * Hook to get the sessions list.
 */
export function useAssistantSessions(): SessionSummary[] {
  return useAssistantStore((s) => s.sessions);
}
