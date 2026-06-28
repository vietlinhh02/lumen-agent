"use client";

import type { StatsData } from "@/lib/stores/projects-store";

const STATS = [
  { key: "project_count" as const, label: "Projects" },
  { key: "paper_count" as const, label: "Papers" },
  { key: "matrix_count" as const, label: "Matrix" },
  { key: "gap_count" as const, label: "Gaps" },
  { key: "report_count" as const, label: "Reports" },
];

interface Props {
  stats: StatsData | null;
}

export function StatsGrid({ stats }: Props) {
  return (
    <div
      data-tour="stats-grid"
      className="w-fit rounded-full bg-primary/[0.06] px-3 py-1.5 font-ui text-[11px] sm:text-[12px]"
      style={{ border: "1px solid rgba(234, 40, 4, 0.22)" }}
    >
      {stats ? (
        <span className="flex flex-wrap gap-x-3 gap-y-0.5">
          {STATS.map((s, i) => (
            <span key={s.key} className="inline-flex items-center gap-1">
              <span className="font-semibold text-primary">{stats[s.key]}</span>
              <span className="text-ink">{s.label}</span>
              {i < STATS.length - 1 && (
                <span className="ml-1 text-primary/40">·</span>
              )}
            </span>
          ))}
        </span>
      ) : (
        <span className="inline-block h-4 w-32 animate-pulse rounded bg-primary/10" />
      )}
    </div>
  );
}
