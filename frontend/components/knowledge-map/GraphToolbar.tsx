"use client";

import { MagnifyingGlass } from "@phosphor-icons/react";

const LAYOUT_OPTIONS = [
  { value: "cose", label: "Force" },
  { value: "breadthfirst", label: "Tree" },
  { value: "concentric", label: "Radial" },
  { value: "circle", label: "Circle" },
  { value: "grid", label: "Grid" },
];

const NODE_TYPE_OPTIONS = [
  { value: "paper", label: "Papers", color: "#3b82f6" },
  { value: "method", label: "Methods", color: "#22c55e" },
  { value: "dataset", label: "Datasets", color: "#f97316" },
  { value: "limitation", label: "Limits", color: "#ef4444" },
];

const MIN_SUPPORT_OPTIONS = [
  { value: 1, label: "All nodes" },
  { value: 2, label: "2+ links" },
  { value: 3, label: "3+ links" },
];

interface Props {
  layout: string;
  onLayoutChange: (layout: string) => void;
  visibleTypes: Set<string>;
  onToggleType: (type: string) => void;
  minConnections: number;
  onMinConnectionsChange: (value: number) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  stats: { paper_count: number; method_count: number; dataset_count: number; limitation_count: number; total_edges: number };
}

export default function GraphToolbar({
  layout,
  onLayoutChange,
  visibleTypes,
  onToggleType,
  minConnections,
  onMinConnectionsChange,
  searchQuery,
  onSearchChange,
  stats,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center rounded-full bg-surface-bone p-1">
        {LAYOUT_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onLayoutChange(opt.value)}
            className={`rounded-full px-3 py-1.5 font-ui text-[12px] font-semibold transition-colors ${
              layout === opt.value
                ? "bg-surface-card text-ink shadow-sm"
                : "text-charcoal hover:text-ink"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {NODE_TYPE_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onToggleType(opt.value)}
          className="flex h-[34px] items-center gap-1.5 rounded-full bg-surface-card px-3 text-[12px] font-semibold transition-all"
          style={{
            background: visibleTypes.has(opt.value) ? `${opt.color}15` : "transparent",
            color: visibleTypes.has(opt.value) ? opt.color : "var(--ash)",
            border: `1px solid ${visibleTypes.has(opt.value) ? `${opt.color}40` : "var(--hairline)"}`,
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: opt.color }} />
          {opt.label}
          <span className="text-[10px] opacity-60">
            {opt.value === "paper" ? stats.paper_count : opt.value === "method" ? stats.method_count : opt.value === "dataset" ? stats.dataset_count : stats.limitation_count}
          </span>
        </button>
      ))}

      <div className="flex items-center rounded-full bg-surface-bone p-1">
        {MIN_SUPPORT_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onMinConnectionsChange(opt.value)}
            className={`rounded-full px-3 py-1.5 font-ui text-[12px] font-semibold transition-colors ${
              minConnections === opt.value
                ? "bg-surface-card text-ink shadow-sm"
                : "text-charcoal hover:text-ink"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="relative ml-auto min-w-[200px]">
        <MagnifyingGlass size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ash" />
        <input
          type="text"
          placeholder="Search papers, methods, datasets…"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="h-[38px] w-full rounded-full border border-[var(--hairline)] bg-surface-card pl-8 pr-4 font-ui text-[13px] text-ink placeholder:text-ash/60 focus:outline-none focus:ring-1 focus:ring-primary/30"
        />
      </div>
    </div>
  );
}
