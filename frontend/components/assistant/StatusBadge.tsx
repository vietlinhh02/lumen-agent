"use client";

import type { AgentStatus } from "@/lib/types";

const LABEL: Record<AgentStatus, { text: string; color: string }> = {
  idle: { text: "Ready", color: "bg-surface-bone text-charcoal" },
  thinking: { text: "Thinking…", color: "bg-yellow-100 text-yellow-800" },
  running: { text: "Running", color: "bg-blue-100 text-blue-800" },
  needs_confirmation: { text: "Awaiting input", color: "bg-orange-100 text-orange-800" },
  stopped: { text: "Stopped", color: "bg-ash/30 text-charcoal" },
  done: { text: "Done", color: "bg-green-100 text-green-800" },
  error: { text: "Error", color: "bg-red-100 text-red-800" },
};

export function StatusBadge({ status, connected }: { status: AgentStatus; connected: boolean }) {
  const { text, color } = LABEL[status];
  return (
    <div className="flex items-center gap-2">
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>{text}</span>
      <span
        className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-gray-400"}`}
        title={connected ? "Connected" : "Disconnected"}
      />
    </div>
  );
}
