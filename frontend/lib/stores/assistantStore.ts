"use client";

import { create } from "zustand";
import type {
  AgentStatus,
  AssistantEvent,
  ChatMessageFE,
  PipelineStep,
  SandboxStatusFE,
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
  /** True when the SSE hook has a project + token and can stream. */
  sseConnected: boolean;
  previewDismissed: boolean;
  // ── Sandbox panel state ──
  sandboxPanelOpen: boolean;
  sandboxStatus: SandboxStatusFE | null;
  sandboxLoading: boolean;
  sandboxError: string | null;
  sandboxToolCalls: number; // total sandbox tools invoked this session
  sandboxLastTool: { name: string; ok: boolean; ts: number } | null;
}

const DEFAULT_PROGRESS: Record<PipelineStep, ProgressState> = {
  create_project: { status: "pending", percent: 0 },
  search_papers: { status: "pending", percent: 0 },
  save_papers: { status: "pending", percent: 0 },
  normalization: { status: "pending", percent: 0 },
  matrix: { status: "pending", percent: 0 },
  gaps: { status: "pending", percent: 0 },
  conflicts: { status: "pending", percent: 0 },
  report: { status: "pending", percent: 0 },
};

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
  sseConnected: false,
  previewDismissed: false,
  sandboxPanelOpen: false,
  sandboxStatus: null,
  sandboxLoading: false,
  sandboxError: null,
  sandboxToolCalls: 0,
  sandboxLastTool: null,
};

const SANDBOX_TOOLS = new Set([
  "run_python",
  "run_shell",
  "read_file",
  "write_file",
  "list_files",
  "open_pdf_page",
  "grep_pdf",
  "install_packages",
]);

type Action = AssistantEvent | { type: "reset" } | {
  type:
    | "set_identity"
    | "set_connected"
    | "append_local_message";
  [k: string]: unknown;
};

function applyEvent(state: AssistantState, e: AssistantEvent): AssistantState {
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
        agentStatus: "idle",
      };
    case "agent_chunk":
      return {
        ...state,
        streamingMessage: `${state.streamingMessage ?? ""}${e.delta}`,
        agentStatus: "running",
      };
    case "tool_call": {
      // Insert a new "running" tool card
      return {
        ...state,
        agentStatus: "running",
        sandboxToolCalls: SANDBOX_TOOLS.has(e.tool)
          ? state.sandboxToolCalls
          : state.sandboxToolCalls,
        messages: [
          ...state.messages,
          {
            role: "tool_log" as const,
            content: `🔧 ${e.tool}`,
            tool_name: e.tool,
            tool_call_id: e.call_id,
            tool_args: e.args ?? null,
            tool_status: "running" as const,
            created_at: new Date().toISOString(),
          },
        ],
      };
    }
    case "tool_result": {
      // Match by call_id; if not found (e.g. history replay) append new card
      const idx = state.messages.findIndex(
        (m) => m.tool_call_id && m.tool_call_id === e.call_id,
      );
      const updated = {
        role: "tool_log" as const,
        content: e.ok ? `✓ ${e.tool}` : `✗ ${e.tool}`,
        tool_name: e.tool,
        tool_call_id: e.call_id,
        tool_args: idx >= 0 ? state.messages[idx].tool_args ?? null : null,
        tool_summary: e.summary,
        tool_duration_ms: e.duration_ms,
        tool_ok: e.ok,
        tool_status: (e.ok ? "ok" : "error") as "ok" | "error",
        created_at: new Date().toISOString(),
      };
      const isSandbox = SANDBOX_TOOLS.has(e.tool);
      const lastTool = isSandbox
        ? { name: e.tool, ok: e.ok, ts: Date.now() }
        : state.sandboxLastTool;
      if (idx >= 0) {
        const messages = [...state.messages];
        messages[idx] = { ...messages[idx], ...updated };
        return {
          ...state,
          agentStatus: "running",
          messages,
          sandboxToolCalls: isSandbox
            ? state.sandboxToolCalls + 1
            : state.sandboxToolCalls,
          sandboxLastTool: lastTool,
        };
      }
      return {
        ...state,
        agentStatus: "running",
        messages: [...state.messages, updated],
        sandboxToolCalls: isSandbox
          ? state.sandboxToolCalls + 1
          : state.sandboxToolCalls,
        sandboxLastTool: lastTool,
      };
    }
    case "log":
      return {
        ...state,
        agentStatus: e.message.toLowerCase().includes("thinking")
          ? "thinking"
          : state.agentStatus,
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

interface AssistantStore {
  state: AssistantState;
  reset: () => void;
  setIdentity: (projectId: string | null, documentId: string | null) => void;
  setConnected: (connected: boolean) => void;
  appendLocalMessage: (msg: ChatMessageFE) => void;
  handleEvent: (event: AssistantEvent) => void;
  togglePreview: () => void;
  toggleSandboxPanel: () => void;
  setSandboxPanel: (open: boolean) => void;
  setSandboxStatus: (status: SandboxStatusFE | null) => void;
  setSandboxLoading: (loading: boolean) => void;
  setSandboxError: (error: string | null) => void;
}

export const useAssistantStore = create<AssistantStore>((set) => ({
  state: initial,
  reset: () =>
    set({ state: { ...initial, progress: { ...DEFAULT_PROGRESS } } }),
  setIdentity: (projectId, documentId) =>
    set((s) => ({ state: { ...s.state, projectId, documentId } })),
  setConnected: (connected) =>
    set((s) => ({ state: { ...s.state, sseConnected: connected } })),
  appendLocalMessage: (msg) =>
    set((s) => ({
      state: {
        ...s.state,
        agentStatus: msg.role === "user" ? "thinking" : s.state.agentStatus,
        messages: [...s.state.messages, msg],
        streamingMessage: msg.role === "user" ? null : s.state.streamingMessage,
      },
    })),
  handleEvent: (event) => set((s) => ({ state: applyEvent(s.state, event) })),
  togglePreview: () =>
    set((s) => ({ state: { ...s.state, previewDismissed: !s.state.previewDismissed } })),
  toggleSandboxPanel: () =>
    set((s) => ({
      state: { ...s.state, sandboxPanelOpen: !s.state.sandboxPanelOpen },
    })),
  setSandboxPanel: (open) =>
    set((s) => ({ state: { ...s.state, sandboxPanelOpen: open } })),
  setSandboxStatus: (status) =>
    set((s) => ({ state: { ...s.state, sandboxStatus: status } })),
  setSandboxLoading: (loading) =>
    set((s) => ({ state: { ...s.state, sandboxLoading: loading } })),
  setSandboxError: (error) =>
    set((s) => ({ state: { ...s.state, sandboxError: error } })),
}));

export type { AssistantState, AssistantStore, Action };
