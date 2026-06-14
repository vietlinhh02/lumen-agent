"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";
import { StatusBadge } from "./StatusBadge";

export function AssistantHeader() {
  const { state, reset } = useAssistantStore();
  return (
    <header className="flex items-center justify-between border-b border-hairline bg-canvas px-6 py-3">
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={reset}
          className="text-xs text-charcoal hover:text-ink"
          title="Back to wizard"
        >
          ← New
        </button>
        <h1 className="font-display text-base font-semibold text-ink truncate">
          {state.documentTitle || "New assistant session"}
        </h1>
        {state.documentVersion > 0 && (
          <span className="text-xs text-charcoal">v{state.documentVersion}</span>
        )}
      </div>
      <StatusBadge status={state.agentStatus} connected={state.wsConnected} />
    </header>
  );
}
