/**
 * Zustand store for the Assistant (ReAct Chat).
 * 
 * Manages:
 * - Session list and selection
 * - SSE event stream handling
 * - ReAct iteration state
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
  SessionDetail,
  SessionStatus,
  ToolArtifact,
  MessageEvent,
  TitleEvent,
  ToolEvent,
  DoneEvent,
  ErrorEvent,
  WaitEvent,
  ThoughtEvent,
  IterationEvent,
  MessageAckEvent,
  AssistantDeltaEvent,
  ProgressEvent,
  ChatResult,
} from "@/lib/types/assistant";

interface ExtendedAssistantState extends AssistantState {
  /** Internal: current chat result for cancellation */
  _chatResult?: ChatResult;
  /** Internal: apply an event to a specific session. */
  _applyEventToSession: (sessionId: string, event: AssistantEventData) => void;
  /** Internal: replace optimistic message with canonical one */
  _replaceOptimisticMessage: (
    sessionId: string,
    clientMessageId: string,
    canonicalId: string
  ) => void;
  /** Internal: extract tool artifact from result */
  _extractToolArtifact: (event: ToolEvent) => void;
  /** Internal: current ReAct iteration info */
  _currentIteration: number;
  _maxIterations: number;
  _currentPhase: "reasoning" | "acting" | null;
  _thoughtBuffers: Map<number, string>;
  _lastToolUsed: string | null;
  /** Internal: accumulator for streaming assistant delta */
  _assistantDeltaBuffer: string;
  /** Internal: ID of the current streaming assistant message */
  _streamingAssistantMessageId: string | null;
  /** Internal: apply assistant delta event */
  _applyAssistantDelta: (sessionId: string, event: AssistantDeltaEvent) => void;
  /** Internal: progress stage tracking */
  _progressStages: Map<string, { progress: number; message: string; timestamp: string }>;
  /** Internal: messages by session (separate from audit events) */
  messagesBySession: Map<string, MessageEvent[]>;
  /** Internal: apply a message event to the messages map */
  _applyMessageEvent: (sessionId: string, event: MessageEvent) => void;
  /** Internal: apply progress event */
  _applyProgress: (event: ProgressEvent) => void;
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
    timestamp: (payload.timestamp as string) ?? timestamp,
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
  messagesBySession: new Map(),
  isStreaming: false,
  currentToolArtifact: null,
  error: null,
  // ReAct iteration state
  _currentIteration: 0,
  _maxIterations: 15,
  _currentPhase: null,
  _thoughtBuffers: new Map(),
  _lastToolUsed: null,
  _assistantDeltaBuffer: "",
  _streamingAssistantMessageId: null,
  _progressStages: new Map(),

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
   * Update the project linked to a session.
   */
  async updateSessionProject(sessionId: string, projectId: string | null) {
    // We do an optimistic update
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId ? { ...s, project_id: projectId } : s
      ),
      currentSession:
        state.currentSession?.id === sessionId
          ? { ...state.currentSession, project_id: projectId }
          : state.currentSession,
    }));

    try {
      await api.updateSessionProject(sessionId, projectId);
      // Fetch full details to get project_title updated
      const detail = await api.getSession(sessionId);
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? { ...s, project_title: detail.project_title } : s
        ),
        currentSession:
          state.currentSession?.id === sessionId
            ? { ...state.currentSession, project_title: detail.project_title }
            : state.currentSession,
      }));
    } catch (err) {
      void get().loadSessions(true);
      set({
        error: err instanceof Error ? err.message : "Failed to update session project",
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

      const newDetail: SessionDetail = {
        id: session.id,
        title: session.title,
        project_id: session.project_id,
        project_title: null,
        status: session.status as SessionStatus,
        created_at: session.created_at,
        updated_at: session.created_at,
        events: [],
      };
      
      set((state) => {
        const eventsMap = new Map(state.events);
        eventsMap.set(session.id, []);

        const messagesMap = new Map(state.messagesBySession);
        messagesMap.set(session.id, []);

        return {
          sessions: [newSummary, ...state.sessions],
          activeSessionId: session.id,
          currentSession: newDetail,
          events: eventsMap,
          messagesBySession: messagesMap,
        };
      });

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
      // Sort session events chronologically by high-precision timestamp
      sessionEvents.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
      eventsMap.set(id, sessionEvents);

      // Extract messages separately for stable chat rendering
      const messagesMap = new Map<string, MessageEvent[]>();
      const sessionMessages = sessionEvents.filter(
        (e) => e.type === "message"
      ) as MessageEvent[];
      messagesMap.set(id, sessionMessages);

      set({
        currentSession: detail,
        events: eventsMap,
        messagesBySession: messagesMap,
        loadingSession: false,
        currentToolArtifact: null,
      });

      // Extract tool artifacts sequentially from historical events
      // so the most recent valid artifact stays active in the ToolPanel.
      for (const e of sessionEvents) {
        if (e.type === "tool") {
          const toolEvent = e as ToolEvent;
          if (toolEvent.status === "called" && toolEvent.result) {
            get()._extractToolArtifact(toolEvent);
          }
        }
      }
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

    // Generate client message ID for deduplication
    const clientMessageId = crypto.randomUUID();

    // Add optimistic user message to events immediately with client ID
    const userMessageEvent: MessageEvent = {
      id: clientMessageId,
      timestamp: new Date().toISOString(),
      type: "message",
      role: "user",
      content: message,
    };

    set((state) => {
      const eventsMap = new Map(state.events);
      const sessionEvents = [...(eventsMap.get(sessionId) ?? []), userMessageEvent];
      eventsMap.set(sessionId, sessionEvents);
      
      // Also add to messagesBySession for stable chat rendering
      const messagesMap = new Map(state.messagesBySession);
      const sessionMessages = [...(messagesMap.get(sessionId) ?? []), userMessageEvent];
      messagesMap.set(sessionId, sessionMessages);
      
      return {
        events: eventsMap,
        messagesBySession: messagesMap,
        isStreaming: true,
        error: null,
        currentToolArtifact: null,
      };
    });

    // Start SSE stream with client message ID
    const chatResult = api.chat(sessionId, message, {
      onMessage: (event: MessageEvent) => {
        // Apply to messages map for chat rendering
        get()._applyMessageEvent(sessionId, event);
        // Also apply to events map for audit/debug
        get()._applyEventToSession(sessionId, event);
      },
      onTitle: (event: TitleEvent) => {
        get()._applyEventToSession(sessionId, event);
        // Update session title in list
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === sessionId ? { ...s, title: event.title } : s
          ),
          currentSession:
            state.currentSession?.id === sessionId
              ? { ...state.currentSession, title: event.title }
              : state.currentSession,
        }));
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
      onThought: (event: ThoughtEvent) => {
        get()._applyEventToSession(sessionId, event);
        // Accumulate thought tokens into buffer for this iteration
        set((state) => {
          const buffers = new Map(state._thoughtBuffers);
          const currentBuffer = buffers.get(event.iteration) || "";
          buffers.set(event.iteration, currentBuffer + event.delta);
          return { _thoughtBuffers: buffers };
        });
      },
      onIteration: (event: IterationEvent) => {
        get()._applyEventToSession(sessionId, event);
        // Reset thought buffer for new iteration if not final
        set((state) => {
          const buffers = new Map(state._thoughtBuffers);
          // Clear thought buffer for new iterations
          if (!buffers.has(event.n)) {
            buffers.set(event.n, "");
          }
          return {
            _currentIteration: event.n,
            _maxIterations: event.max,
            _currentPhase: event.phase,
            _thoughtBuffers: buffers,
          };
        });
      },
      onMessageAck: (event: MessageAckEvent) => {
        // Replace optimistic message with canonical one
        get()._replaceOptimisticMessage(sessionId, event.client_message_id, event.canonical_id);
      },
      onAssistantDelta: (event: AssistantDeltaEvent) => {
        get()._applyAssistantDelta(sessionId, event);
      },
      onProgress: (event: ProgressEvent) => {
        get()._applyProgress(event);
      },
    }, clientMessageId);

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
      const existingEvents = state.events.get(sessionId);
      
      // Deduplication: Check by ID first, then by turn_id for events with the same turn
      // This ensures stable event order even when timestamps are equal or DB precision differs
      const isDuplicate = existingEvents?.some((e) => {
        // Exact ID match
        if (e.id === event.id) return true;
        // For messages, also check turn_id to avoid duplicates from optimistic UI
        if (
          event.turn_id &&
          e.turn_id === event.turn_id &&
          e.type === event.type &&
          (e as MessageEvent).role === (event as MessageEvent).role
        ) {
          return true;
        }
        return false;
      });
      
      if (isDuplicate) {
        // Duplicate event, skip processing
        return state;
      }

      // Efficiently append the new event to the existing array
      const eventsMap = new Map(state.events);
      const sessionEvents = existingEvents ? [...existingEvents, event] : [event];
      eventsMap.set(sessionId, sessionEvents);

      // Track last tool used for IterationPanel
      let lastToolUsed = state._lastToolUsed;
      if (event.type === "tool") {
        const toolEvent = event as ToolEvent;
        if (toolEvent.status === "called") {
          lastToolUsed = toolEvent.function;
        }
      }

      // Initialize sessions from state
      let sessions = state.sessions;

      // Update session status in list for done/error events
      const eventType = event.type;
      if (eventType === "done" || eventType === "error") {
        const newStatus = eventType === "done" ? "completed" : "failed";
        sessions = state.sessions.map((s) =>
          s.id === sessionId ? { ...s, status: newStatus as SessionSummary["status"] } : s
        );
      }

      // Reset iteration state when done or waiting
      if (eventType === "done" || eventType === "wait") {
        return {
          events: eventsMap,
          sessions,
          _currentIteration: 0,
          _currentPhase: null,
          _thoughtBuffers: new Map(),
          _lastToolUsed: null,
        };
      }

      return {
        events: eventsMap,
        sessions,
        _lastToolUsed: lastToolUsed,
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

  /**
   * Apply an assistant delta event, accumulating tokens into the streaming message.
   * Creates or updates the assistant message in place.
   */
  _applyAssistantDelta(sessionId: string, event: AssistantDeltaEvent) {
    set((state) => {
      const eventsMap = state.events.get(sessionId);
      const messagesMap = state.messagesBySession;
      if (!eventsMap) return state;

      const existingEvents = [...eventsMap];
      const existingMessages = [...(messagesMap.get(sessionId) ?? [])];
      
      // Find or create the streaming assistant message in events
      let messageIndex = existingEvents.findIndex(
        (e) => e.type === "message" && (e as MessageEvent).role === "assistant" &&
        (e as MessageEvent).id === state._streamingAssistantMessageId
      );

      // If no streaming message exists, create one
      if (messageIndex === -1) {
        const streamingId = `streaming-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
        const newMessage: MessageEvent = {
          id: streamingId,
          timestamp: new Date().toISOString(),
          type: "message",
          role: "assistant",
          content: event.delta,
          turn_id: event.turn_id ?? undefined,
        };
        existingEvents.push(newMessage);
        // Only push to existingMessages if not already present (dedupe by ID)
        if (!existingMessages.some((m) => m.id === streamingId)) {
          existingMessages.push(newMessage);
        }
        
        return {
          events: new Map(state.events).set(sessionId, existingEvents),
          messagesBySession: new Map(messagesMap).set(sessionId, existingMessages),
          _assistantDeltaBuffer: event.delta,
          _streamingAssistantMessageId: streamingId,
        };
      }

      // Update existing streaming message by accumulating deltas
      // Use the message's existing content to avoid losing data if buffer is stale
      const existingMessage = existingEvents[messageIndex] as MessageEvent;
      const previousContent = existingMessage.content || "";
      const updatedContent = previousContent + event.delta;
      const updatedMessage: MessageEvent = {
        ...existingMessage,
        content: updatedContent,
      };

      const updatedEvents = [...existingEvents];
      updatedEvents[messageIndex] = updatedMessage;

      // IMPORTANT: ``messageIndex`` is the position in ``existingEvents``
      // (all events), not in ``existingMessages`` (message-only). Look up
      // the same message by id in the messages array so we never create a
      // sparse array by using the wrong index.
      const messageIndexInMessages = existingMessages.findIndex(
        (m) => m?.id === updatedMessage.id
      );
      const updatedMessages =
        messageIndexInMessages >= 0
          ? existingMessages.map((m, i) =>
              i === messageIndexInMessages ? updatedMessage : m
            )
          : [...existingMessages, updatedMessage];

      // Clear streaming state when final delta arrives
      if (event.is_final) {
        return {
          events: new Map(state.events).set(sessionId, updatedEvents),
          messagesBySession: new Map(messagesMap).set(sessionId, updatedMessages),
          _assistantDeltaBuffer: "",
          _streamingAssistantMessageId: null,
        };
      }

      return {
        events: new Map(state.events).set(sessionId, updatedEvents),
        messagesBySession: new Map(messagesMap).set(sessionId, updatedMessages),
        _assistantDeltaBuffer: updatedContent,
      };
    });
  },

  /**
   * Apply a progress event, tracking the latest progress per stage.
   */
  _applyProgress(event: ProgressEvent) {
    set((state) => {
      const stages = new Map(state._progressStages);
      stages.set(event.stage, {
        progress: event.progress,
        message: event.message,
        timestamp: event.timestamp,
      });
      return { _progressStages: stages };
    });
  },

  /**
   * Apply a message event to the messages map.
   * Messages are stored separately from audit events for stable chat rendering.
   * If this is the canonical assistant message (from backend after save),
   * it replaces the streaming message with the canonical ID.
   */
  _applyMessageEvent(sessionId: string, event: MessageEvent) {
    set((state) => {
      const messagesMap = new Map(state.messagesBySession);
      const existingMessages = messagesMap.get(sessionId) ?? [];

      // Check for duplicate by ID
      const existingIndex = existingMessages.findIndex((m) => m.id === event.id);
      if (existingIndex >= 0) {
        // Update existing message in place
        const updatedMessages = [...existingMessages];
        updatedMessages[existingIndex] = event;
        messagesMap.set(sessionId, updatedMessages);
        return { messagesBySession: messagesMap };
      }

      // If this is an assistant message, try to replace the streaming message
      // (the streaming ID might already be cleared if final delta was processed first)
      if (event.role === "assistant") {
        // First try to find by tracked streaming ID
        let streamingIndex = -1;
        if (state._streamingAssistantMessageId !== null) {
          streamingIndex = existingMessages.findIndex(
            (m) => m.id === state._streamingAssistantMessageId
          );
        }

        // If not found, look for any assistant message with streaming- prefix
        // (this handles the case where the final delta arrived first)
        if (streamingIndex === -1) {
          streamingIndex = existingMessages.findIndex(
            (m) => m.role === "assistant" && m.id.startsWith("streaming-")
          );
        }

        if (streamingIndex >= 0) {
          // Replace streaming message with canonical
          const updatedMessages = [...existingMessages];
          updatedMessages[streamingIndex] = event;
          messagesMap.set(sessionId, updatedMessages);
          return {
            messagesBySession: messagesMap,
            _streamingAssistantMessageId: null,
            _assistantDeltaBuffer: "",
          };
        }
      }

      // Append new message (avoid duplicates)
      // Guard against malformed events missing id (defensive)
      if (!event.id) {
        return state;
      }
      if (!existingMessages.some((m) => m?.id === event.id)) {
        messagesMap.set(sessionId, [...existingMessages, event]);
      }

      return { messagesBySession: messagesMap };
    });
  },

  /**
   * Replace an optimistic message with the canonical one from the backend.
   * This ensures the optimistic UI message gets the correct ID from the server.
   */
  _replaceOptimisticMessage(
    sessionId: string,
    clientMessageId: string,
    canonicalId: string
  ) {
    set((state) => {
      const eventsMap = state.events.get(sessionId);
      if (!eventsMap) return state;

      // Find and replace the optimistic message
      const updatedEvents = eventsMap.map((event) => {
        if (event.id === clientMessageId && event.type === "message") {
          // Replace with canonical ID but keep other properties
          return {
            ...event,
            id: canonicalId,
          } as MessageEvent;
        }
        return event;
      });

      const newEventsMap = new Map(state.events);
      newEventsMap.set(sessionId, updatedEvents);
      return { events: newEventsMap };
    });
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
    } else {
      // Fallback for all other tools: raw JSON view
      artifact = {
        type: event.function,
        title: event.function.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
        data: result,
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
      messagesBySession: new Map(),
      isStreaming: false,
      currentToolArtifact: null,
      error: null,
      _chatResult: undefined,
      _currentIteration: 0,
      _maxIterations: 15,
      _currentPhase: null,
      _thoughtBuffers: new Map(),
      _lastToolUsed: null,
      _assistantDeltaBuffer: "",
      _streamingAssistantMessageId: null,
      _progressStages: new Map(),
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

/**
 * Hook to get the current iteration info for ReAct agent.
 */
export function useCurrentIteration(): {
  iteration: number;
  max: number;
  phase: "reasoning" | "acting" | null;
} {
  const iteration = useAssistantStore((s) => s._currentIteration);
  const max = useAssistantStore((s) => s._maxIterations);
  const phase = useAssistantStore((s) => s._currentPhase);
  return { iteration, max, phase };
}

/**
 * Hook to get the current thought buffer for streaming display.
 */
export function useCurrentThought(): string {
  const iteration = useAssistantStore((s) => s._currentIteration);
  const buffers = useAssistantStore((s) => s._thoughtBuffers);
  return buffers.get(iteration) ?? "";
}

/**
 * Hook to get all thought buffers (for displaying previous iterations).
 */
export function useThoughtBuffers(): Map<number, string> {
  return useAssistantStore((s) => s._thoughtBuffers);
}

/**
 * Hook to get the last tool used.
 */
export function useLastToolUsed(): string | null {
  return useAssistantStore((s) => s._lastToolUsed);
}

/**
 * Hook to get the current progress stages for pipeline display.
 */
export function useProgressStages(): Map<string, { progress: number; message: string; timestamp: string }> {
  return useAssistantStore((s) => s._progressStages);
}

/**
 * Hook to get messages for the active session.
 * Messages are stored separately from audit events for stable chat rendering.
 */
export function useMessages(): MessageEvent[] {
  const sessionId = useAssistantStore((s) => s.activeSessionId);
  const messagesMap = useAssistantStore((s) => s.messagesBySession);
  if (!sessionId) return [];
  return messagesMap.get(sessionId) ?? [];
}
