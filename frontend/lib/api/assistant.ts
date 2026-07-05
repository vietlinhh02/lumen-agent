/**
 * API client for the Assistant endpoints.
 * 
 * Provides functions for:
 * - Session CRUD operations
 * - Chat with SSE streaming
 * - Session control (stop)
 */

import { fetchEventSource } from "@microsoft/fetch-event-source";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/lib/stores/auth-store";
import type {
  SessionCreate,
  SessionResponse,
  SessionListResponse,
  SessionDetail,
  ChatRequest,
  SSEEvent,
  AssistantEventData,
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
  ActionEvent,
} from "@/lib/types/assistant";

// ── Type Helpers ───────────────────────────────────────────────────────────────

function getToken(): string | null {
  return useAuthStore.getState().token;
}

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ── Session CRUD ───────────────────────────────────────────────────────────────

/**
 * Create a new assistant session.
 */
export async function createSession(data?: SessionCreate): Promise<SessionResponse> {
  return apiFetch<SessionResponse>("/assistant/sessions", {
    method: "PUT",
    body: JSON.stringify(data ?? {}),
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
  });
}

/**
 * Get a session by ID with all events and plan.
 * Used for replaying session history.
 */
export async function getSession(sessionId: string): Promise<SessionDetail> {
  return apiFetch<SessionDetail>(`/assistant/sessions/${sessionId}`, {
    headers: authHeaders(),
  });
}

/**
 * List all sessions for the current user.
 */
export async function listSessions(
  limit = 50,
  offset = 0
): Promise<SessionListResponse> {
  return apiFetch<SessionListResponse>(
    `/assistant/sessions?limit=${limit}&offset=${offset}`,
    { headers: authHeaders() }
  );
}

/**
 * Delete a session and all its events.
 */
export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch<void>(`/assistant/sessions/${sessionId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

/**
 * Rename a session.
 */
export async function updateSessionTitle(
  sessionId: string,
  title: string
): Promise<SessionResponse> {
  return apiFetch<SessionResponse>(
    `/assistant/sessions/${sessionId}/title`,
    {
      method: "PATCH",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }
  );
}

/**
 * Update the project linked to a session.
 */
export async function updateSessionProject(
  sessionId: string,
  projectId: string | null
): Promise<SessionResponse> {
  return apiFetch<SessionResponse>(
    `/assistant/sessions/${sessionId}/project`,
    {
      method: "PATCH",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId }),
    }
  );
}

/**
 * Stop a running chat session.
 * Returns immediately; the SSE stream will end with cancellation events.
 */
export async function stopSession(sessionId: string): Promise<void> {
  await apiFetch<void>(`/assistant/sessions/${sessionId}/stop`, {
    method: "POST",
    headers: authHeaders(),
  });
}

// ── SSE Chat ───────────────────────────────────────────────────────────────────

/**
 * Event handlers for the chat stream.
 */
export interface ChatEventHandlers {
  onMessage?: (event: MessageEvent) => void;
  onTitle?: (event: TitleEvent) => void;
  onTool?: (event: ToolEvent) => void;
  onDone?: (event: DoneEvent) => void;
  onError?: (event: ErrorEvent) => void;
  onWait?: (event: WaitEvent) => void;
  onThought?: (event: ThoughtEvent) => void;
  onIteration?: (event: IterationEvent) => void;
  onMessageAck?: (event: MessageAckEvent) => void;
  onAssistantDelta?: (event: AssistantDeltaEvent) => void;
  onProgress?: (event: ProgressEvent) => void;
  onAction?: (event: ActionEvent) => void;
  onAny?: (event: AssistantEventData, eventName: string) => void;
}

/**
 * Chat result with cancel function.
 */
export interface ChatResult {
  /** Call this to cancel the stream */
  cancel: () => void;
  /** Promise that resolves when the stream ends */
  finished: Promise<void>;
}

/**
 * Send a chat message and receive SSE stream of events.
 * 
 * Uses fetch-event-source for POST + SSE.
 * 
 * @param sessionId - The session ID to chat in
 * @param message - The user's message
 * @param handlers - Event handlers for each event type
 * @param clientMessageId - Optional client-generated ID for deduplication
 * @returns ChatResult with cancel function
 */
export function chat(
  sessionId: string,
  message: string,
  handlers: ChatEventHandlers = {},
  clientMessageId?: string,
  action?: string
): ChatResult {
  const controller = new AbortController();
  
  const finished = new Promise<void>((resolve, reject) => {
    (async () => {
      const signal = controller.signal;
      
      try {
        const token = getToken();
        if (!token) {
          throw new Error("Authentication required");
        }

        // Build request body with optional client_message_id and action
        const requestBody: Record<string, unknown> = { message };
        if (clientMessageId) {
          requestBody.client_message_id = clientMessageId;
        }
        if (action) {
          requestBody.action = action;
        }

        await fetchEventSource(`/api/assistant/sessions/${sessionId}/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(requestBody),
          signal,
          openWhenHidden: true,
          async onopen(response) {
            if (response.ok) {
              return;
            }

            const errorData = await response.json().catch(() => ({}));
            const detail = errorData.detail ?? `Request failed (${response.status})`;
            throw new Error(
              typeof detail === "string" ? detail : JSON.stringify(detail)
            );
          },
          onmessage(event) {
            if (!event.data) {
              return;
            }

            try {
              const eventName = event.event || "message";
              const eventData = JSON.parse(event.data) as Partial<AssistantEventData>;
              dispatchEvent(
                {
                  event: eventName,
                  data: {
                    type: eventName,
                    ...eventData,
                  } as AssistantEventData,
                },
                handlers
              );
            } catch {
              // Ignore malformed events; the stream may continue with valid events.
            }
          },
          onerror(error) {
            throw error;
          },
          onclose() {
            // Stream was closed normally or aborted
            // Resolve the promise to signal completion
            resolve();
          }
        });
        
        resolve();
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          resolve(); // Cancelled, not an error
        } else {
          reject(err);
        }
      }
    })();
  });
  
  return {
    cancel: () => {
      controller.abort();
    },
    finished,
  };
}

/**
 * Send a deep research message through the normal chat endpoint.
 * Uses the `action` field in ChatRequest to trigger deep research flow.
 * 
 * @deprecated Use `chat()` with `action: "start_deep_research"` instead.
 */
export function research(
  sessionId: string,
  message: string,
  handlers: ChatEventHandlers = {},
  clientMessageId?: string,
  action: string = "start"
): ChatResult {
  return chat(sessionId, message, handlers, clientMessageId, action);
}

/**
 * Dispatch an SSE event to the appropriate handler.
 */
function dispatchEvent(
  sseEvent: SSEEvent,
  handlers: ChatEventHandlers
): void {
  const { event: eventName, data } = sseEvent;
  const eventType = data.type || eventName;
  
  // Call type-specific handler
  switch (eventType) {
    case "message":
      handlers.onMessage?.(data as MessageEvent);
      break;
    case "title":
      handlers.onTitle?.(data as TitleEvent);
      break;
    case "tool":
      handlers.onTool?.(data as ToolEvent);
      break;
    case "done":
      handlers.onDone?.(data as DoneEvent);
      break;
    case "error":
      handlers.onError?.(data as ErrorEvent);
      break;
    case "wait":
      handlers.onWait?.(data as WaitEvent);
      break;
    case "thought":
      handlers.onThought?.(data as ThoughtEvent);
      break;
    case "iteration":
      handlers.onIteration?.(data as IterationEvent);
      break;
    case "message_ack":
      handlers.onMessageAck?.(data as MessageAckEvent);
      break;
    case "assistant_delta":
      handlers.onAssistantDelta?.(data as AssistantDeltaEvent);
      break;
    case "progress":
      handlers.onProgress?.(data as ProgressEvent);
      break;
    case "action":
      handlers.onAction?.(data as ActionEvent);
      break;
  }
  
  // Call generic handler for any event
  handlers.onAny?.(data, eventName);
}

// ── Re-export types for convenience ───────────────────────────────────────────

export type {
  AssistantEventData,
  SessionCreate,
  SessionResponse,
  SessionListResponse,
  SessionDetail,
  ChatRequest,
  SSEEvent,
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
  ActionEvent,
};

// ── Deep Research ────────────────────────────────────────────────────────────

import type {
  DeepResearchJobResponse,
} from "@/lib/types/assistant";

/**
 * Fetch the current status of a Deep Research job.
 */
export async function fetchDeepResearchJob(
  sessionId: string,
  jobId: string
): Promise<DeepResearchJobResponse> {
  return apiFetch<DeepResearchJobResponse>(
    `/assistant/sessions/${sessionId}/research/${jobId}`,
    { headers: authHeaders() }
  );
}

/**
 * Connect to the Deep Research SSE stream for real-time job progress.
 */
export function streamDeepResearchJob(
  sessionId: string,
  jobId: string,
  handlers: {
    onProgress?: (event: ProgressEvent) => void;
    onAssistantDelta?: (event: AssistantDeltaEvent) => void;
    onDone?: (event: DoneEvent) => void;
    onError?: (event: ErrorEvent) => void;
  }
): ChatResult {
  const controller = new AbortController();

  const finished = new Promise<void>((resolve, reject) => {
    (async () => {
      const signal = controller.signal;

      try {
        const token = getToken();
        if (!token) {
          throw new Error("Authentication required");
        }

        await fetchEventSource(
          `/api/assistant/sessions/${sessionId}/research/${jobId}/stream`,
          {
            method: "GET",
            headers: {
              Authorization: `Bearer ${token}`,
            },
            signal,
            openWhenHidden: true,
            async onopen(response) {
              if (response.ok) return;
              const errorData = await response.json().catch(() => ({}));
              throw new Error(errorData.detail ?? `Stream failed (${response.status})`);
            },
            onmessage(event) {
              if (!event.data) return;
              try {
                const eventName = event.event || "progress";
                const eventData = JSON.parse(event.data) as Record<string, unknown>;

                switch (eventName) {
                  case "progress":
                    handlers.onProgress?.({
                      type: "progress",
                      ...eventData,
                    } as ProgressEvent);
                    break;
                  case "assistant_delta":
                    handlers.onAssistantDelta?.({
                      type: "assistant_delta",
                      ...eventData,
                    } as AssistantDeltaEvent);
                    break;
                  case "done":
                    handlers.onDone?.({
                      type: "done",
                      ...eventData,
                    } as DoneEvent);
                    break;
                  case "error":
                    handlers.onError?.({
                      type: "error",
                      ...eventData,
                    } as ErrorEvent);
                    break;
                }
              } catch {
                // Ignore malformed events
              }
            },
            onerror(error) {
              console.error("streamDeepResearchJob: fetchEventSource error:", error);
              handlers.onError?.({
                type: "error",
                code: "STREAM_ERROR",
                message: error instanceof Error ? error.message : String(error),
              } as ErrorEvent);
              throw error;
            },
            onclose() {
              resolve();
            },
          }
        );

        resolve();
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          resolve();
        } else {
          reject(err);
        }
      }
    })();
  });

  return {
    cancel: () => controller.abort(),
    finished,
  };
}
