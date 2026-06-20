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
    <div className="mb-5 grid grid-cols-5 gap-1.5 sm:mb-8 sm:gap-3 lg:gap-4">
      {stats
        ? STATS.map((s) => {
            const value = stats[s.key];
            return (
              <div
                key={s.key}
                className="flex min-h-[74px] flex-col items-center justify-center rounded-[10px] bg-surface-card px-1.5 py-2 text-center sm:min-h-[108px] sm:rounded-[14px] sm:p-4 lg:min-h-[120px]"
                style={{ border: "1px solid var(--hairline)" }}
              >
                <div className={`mb-1.5 flex h-7 w-7 items-center justify-center rounded-[8px] sm:mb-2 sm:h-10 sm:w-10 sm:rounded-[10px] ${s.bg}`}>
                  <s.icon size={15} weight="duotone" className={s.color} />
                </div>
                <p className="font-display text-[18px] font-bold leading-none text-ink sm:text-[24px] lg:text-[26px]">
                  {value}
                </p>
                <p className="mt-1 max-w-full truncate font-ui text-[9px] font-medium leading-tight text-ash sm:text-[11px]">
                  {s.label}
                </p>
              </div>
            );
          })
        : [1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex min-h-[74px] flex-col items-center justify-center rounded-[10px] bg-surface-card px-1.5 py-2 animate-pulse sm:min-h-[108px] sm:rounded-[14px] sm:p-4" style={{ border: "1px solid var(--hairline)" }}>
              <div className="mb-2 h-7 w-7 rounded-[8px] bg-surface-bone sm:h-10 sm:w-10 sm:rounded-[10px]" />
              <div className="mb-1 h-5 w-8 rounded bg-surface-bone sm:h-6 sm:w-10" />
              <div className="h-2.5 w-10 rounded bg-surface-bone sm:h-3 sm:w-14" />
            </div>
          ))}
    </div>
  );
}
