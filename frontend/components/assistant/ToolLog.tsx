"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";

export function ToolLog() {
  const { state } = useAssistantStore();
  const logs = state.currentLog;
  if (logs.length === 0) return null;
  return (
    <details className="border-t border-hairline bg-surface-bone/50 px-4 py-2">
      <summary className="text-xs text-charcoal cursor-pointer">
        Activity log ({logs.length})
      </summary>
      <div className="mt-2 space-y-1 max-h-32 overflow-y-auto">
        {logs.slice(-20).map((log, i) => (
          <div
            key={i}
            className={`text-xs font-mono ${
              log.level === "error" ? "text-red-700" : "text-charcoal/80"
            }`}
          >
            {log.message}
          </div>
        ))}
      </div>
    </details>
  );
}
