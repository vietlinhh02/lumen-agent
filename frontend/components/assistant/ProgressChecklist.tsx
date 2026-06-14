"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";
import type { PipelineStep } from "@/lib/types";

const STEPS: { key: PipelineStep; label: string }[] = [
  { key: "create_project", label: "Create project" },
  { key: "search_papers", label: "Search papers" },
  { key: "save_papers", label: "Save papers" },
  { key: "matrix", label: "Generate matrix" },
  { key: "gaps", label: "Detect gaps" },
  { key: "report", label: "Write report" },
];

export function ProgressChecklist() {
  const { state } = useAssistantStore();
  const progress = state.progress;
  return (
    <div className="border-b border-hairline bg-surface-bone/40 px-4 py-3">
      <ul className="space-y-1.5 text-sm">
        {STEPS.map(({ key, label }) => {
          const p = progress[key];
          const icon =
            p.status === "done" ? "✓" :
            p.status === "running" ? "▶" :
            p.status === "failed" ? "✗" :
            "○";
          const color =
            p.status === "done" ? "text-green-700" :
            p.status === "running" ? "text-blue-700" :
            p.status === "failed" ? "text-red-700" :
            "text-charcoal/50";
          return (
            <li key={key} className={`flex items-center gap-2 ${color}`}>
              <span className="w-4 inline-block text-center font-mono">{icon}</span>
              <span className="flex-1">{label}</span>
              {p.status === "running" && (
                <span className="text-xs text-charcoal/60">{p.percent}%</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
