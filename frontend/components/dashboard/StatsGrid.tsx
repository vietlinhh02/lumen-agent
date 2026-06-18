"use client";

import { Folder, FileText, Table, Lightbulb, PencilLine } from "@phosphor-icons/react";
import type { StatsData } from "@/lib/stores/projects-store";

const STATS = [
  { key: "project_count" as const, label: "Projects", icon: Folder, color: "text-primary", bg: "bg-primary/10" },
  { key: "paper_count" as const, label: "Papers", icon: FileText, color: "text-amber-600", bg: "bg-amber-50" },
  { key: "matrix_count" as const, label: "Matrix Rows", icon: Table, color: "text-emerald-600", bg: "bg-emerald-50" },
  { key: "gap_count" as const, label: "Research Gaps", icon: Lightbulb, color: "text-violet-600", bg: "bg-violet-50" },
  { key: "report_count" as const, label: "Reports", icon: PencilLine, color: "text-blue-600", bg: "bg-blue-50" },
];

interface Props {
  stats: StatsData | null;
}

export function StatsGrid({ stats }: Props) {
  return (
    <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
      {stats
        ? STATS.map((s) => {
            const value = stats[s.key];
            return (
              <div
                key={s.key}
                className="flex flex-col items-center justify-center rounded-[16px] bg-surface-card p-5 text-center"
                style={{ border: "1px solid var(--hairline)" }}
              >
                <div className={`mb-3 flex h-12 w-12 items-center justify-center rounded-[12px] ${s.bg}`}>
                  <s.icon size={22} weight="duotone" className={s.color} />
                </div>
                <p className="font-display text-[28px] font-bold leading-none text-ink">{value}</p>
                <p className="mt-1 font-ui text-[12px] font-medium text-ash">{s.label}</p>
              </div>
            );
          })
        : [1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex flex-col items-center justify-center rounded-[16px] bg-surface-card p-5 animate-pulse" style={{ border: "1px solid var(--hairline)" }}>
              <div className="mb-3 h-12 w-12 rounded-[12px] bg-surface-bone" />
              <div className="mb-1 h-7 w-12 rounded bg-surface-bone" />
              <div className="h-3 w-16 rounded bg-surface-bone" />
            </div>
          ))}
    </div>
  );
}
