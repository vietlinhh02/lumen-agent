"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import type {
  AgentStatus,
  AssistantEvent,
  ChatMessageFE,
  PipelineStep,
} from "@/lib/types";

interface ProgressState {
  status: "pending" | "running" | "done" | "failed";
  percent: number;
  label?: string;
}

interface AssistantState {
  projectId: string | null;
  documentId: string | null;
  sessionId: string | null;
  messages: ChatMessageFE[];
  streamingMessage: string | null;
  currentMarkdown: string;
  documentVersion: number;
  documentTitle: string;
  progress: Record<PipelineStep, ProgressState>;
  currentLog: Array<{ level: "info" | "warn" | "error"; message: string }>;
  agentStatus: AgentStatus;
  ws: WebSocket | null;
  wsConnected: boolean;
}

const DEFAULT_PROGRESS: Record<PipelineStep, ProgressState> = {
  create_project: { status: "pending", percent: 0 },
  search_papers: { status: "pending", percent: 0 },
  save_papers: { status: "pending", percent: 0 },
  matrix: { status: "pending", percent: 0 },
  gaps: { status: "pending", percent: 0 },
  report: { status: "pending", percent: 0 },
};

type Action =
  | { type: "reset" }
  | { type: "set_identity"; projectId: string | null; documentId: string | null }
  | { type: "set_ws"; ws: WebSocket | null }
  | { type: "set_connected"; connected: boolean }
  | { type: "append_local_message"; msg: ChatMessageFE }
  | { type: "event"; event: AssistantEvent };

const initial: AssistantState = {
  projectId: null,
  documentId: null,
  sessionId: null,
  messages: [],
  streamingMessage: null,
  currentMarkdown: "",
  documentVersion: 0,
  documentTitle: "",
  progress: { ...DEFAULT_PROGRESS },
  currentLog: [],
  agentStatus: "idle",
  ws: null,
  wsConnected: false,
};

function reducer(state: AssistantState, action: Action): AssistantState {
  switch (action.type) {
    case "reset":
      return { ...initial, progress: { ...DEFAULT_PROGRESS } };
    case "set_identity":
      return { ...state, projectId: action.projectId, documentId: action.documentId };
    case "set_ws":
      return { ...state, ws: action.ws };
    case "set_connected":
      return { ...state, wsConnected: action.connected };
    case "append_local_message":
      return { ...state, messages: [...state.messages, action.msg] };
    case "event": {
      const e = action.event;
      switch (e.type) {
        case "connected":
          return {
            ...state,
            sessionId: e.session_id,
            projectId: e.project_id || state.projectId,
            documentId: e.document_id || state.documentId,
            agentStatus: "idle",
          };
        case "project_created":
          return { ...state, projectId: e.project_id, documentId: e.document_id };
        case "markdown_snapshot":
          return {
            ...state,
            currentMarkdown: e.content,
            documentVersion: e.version,
            documentTitle: e.title,
          };
        case "markdown_updated":
          return { ...state, currentMarkdown: e.content, documentVersion: e.version };
        case "message_history":
          return { ...state, messages: e.messages };
        case "agent_message":
          return {
            ...state,
            messages: [
              ...state.messages,
              { role: "assistant", content: e.content, created_at: new Date().toISOString() },
            ],
            streamingMessage: null,
          };
        case "tool_call":
        case "tool_result":
          return {
            ...state,
            messages: [
              ...state.messages,
              {
                role: "tool_log",
                content:
                  e.type === "tool_call"
                    ? `🔧 ${e.tool}`
                    : `${e.ok ? "✓" : "✗"} ${e.tool}: ${e.summary.slice(0, 200)}`,
                tool_name: e.tool,
                created_at: new Date().toISOString(),
              },
            ],
          };
        case "log":
          return {
            ...state,
            currentLog: [...state.currentLog, { level: e.level, message: e.message }].slice(-50),
          };
        case "progress": {
          const step = e.step as PipelineStep;
          if (step in state.progress) {
            return {
              ...state,
              progress: {
                ...state.progress,
                [step]: { status: e.status, percent: e.percent, label: e.label },
              },
            };
          }
          return state;
        }
        case "done":
          return { ...state, agentStatus: "done" };
        case "stopped":
          return { ...state, agentStatus: "stopped" };
        case "error":
          return {
            ...state,
            agentStatus: "error",
            currentLog: [
              ...state.currentLog,
              { level: "error", message: `${e.code}: ${e.message}` },
            ],
          };
        case "needs_confirmation":
          return { ...state, agentStatus: "needs_confirmation" };
        default:
          return state;
      }
    }
    default:
      return state;
  }
}

type AssistantContext = {
  state: AssistantState;
  reset: () => void;
  setIdentity: (projectId: string | null, documentId: string | null) => void;
  setWs: (ws: WebSocket | null) => void;
  setConnected: (connected: boolean) => void;
  appendLocalMessage: (msg: ChatMessageFE) => void;
  handleEvent: (event: AssistantEvent) => void;
};

const Ctx = createContext<AssistantContext | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);

  const reset = useCallback(() => dispatch({ type: "reset" }), []);
  const setIdentity = useCallback(
    (projectId: string | null, documentId: string | null) =>
      dispatch({ type: "set_identity", projectId, documentId }),
    [],
  );
  const setWs = useCallback(
    (ws: WebSocket | null) => dispatch({ type: "set_ws", ws }),
    [],
  );
  const setConnected = useCallback(
    (connected: boolean) => dispatch({ type: "set_connected", connected }),
    [],
  );
  const appendLocalMessage = useCallback(
    (msg: ChatMessageFE) => dispatch({ type: "append_local_message", msg }),
    [],
  );
  const handleEvent = useCallback(
    (event: AssistantEvent) => dispatch({ type: "event", event }),
    [],
  );

  const value = useMemo<AssistantContext>(
    () => ({ state, reset, setIdentity, setWs, setConnected, appendLocalMessage, handleEvent }),
    [state, reset, setIdentity, setWs, setConnected, appendLocalMessage, handleEvent],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAssistantStore(): AssistantContext {
  const ctx = useContext(Ctx);
  if (!ctx) {
    throw new Error("useAssistantStore must be used within AssistantProvider");
  }
  return ctx;
}
