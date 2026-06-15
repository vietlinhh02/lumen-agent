"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";
import type { PipelineStep } from "@/lib/types";

const STEPS: { key: PipelineStep; label: string }[] = [
  { key: "create_project", label: "Create project" },
  { key: "search_papers", label: "Search papers" },
  { key: "save_papers", label: "Save papers" },
  { key: "normalization", label: "Normalize PDFs" },
  { key: "matrix", label: "Generate matrix" },
  { key: "gaps", label: "Detect gaps" },
  { key: "conflicts", label: "Detect conflicts" },
  { key: "report", label: "Write report" },
];

export function ProgressChecklist() {
  const { state } = useAssistantStore();
  const progress = state.progress;
  return (
    <div className="bg-surface-bone/40 px-2 py-2 md:px-4">
      <ol className="flex items-center gap-2 text-[11px] md:text-xs overflow-x-auto whitespace-nowrap scrollbar-hide">
        {STEPS.map(({ key, label }, i) => {
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
            <li
              key={key}
              className={`flex shrink-0 items-center gap-2 rounded-full border border-hairline bg-canvas px-2.5 py-1 ${color}`}
            >
              {i > 0 && <span className="hidden md:inline text-charcoal/30">·</span>}
              <span className="flex items-center gap-1.5 min-w-0">
                <span className="w-3 inline-block text-center font-mono">{icon}</span>
                <span className="hidden sm:inline">{label}</span>
                {p.status === "running" && (
                  <span className="text-charcoal/60">{p.percent}%</span>
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
