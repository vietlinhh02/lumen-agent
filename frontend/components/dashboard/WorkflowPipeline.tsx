"use client";

import {
  MagnifyingGlass,
  Folder,
  Table,
  Graph,
  Lightbulb,
  PencilLine,
} from "@phosphor-icons/react";
import type { IconProps } from "@phosphor-icons/react";

export type PipelineStepKey =
  | "search"
  | "save"
  | "matrix"
  | "map"
  | "gaps"
  | "report";

export interface PipelineStep {
  key: PipelineStepKey;
  label: string;
  number: string;
  icon: React.ComponentType<IconProps>;
}

export const PIPELINE_STEPS: PipelineStep[] = [
  { key: "search", label: "Search", number: "01", icon: MagnifyingGlass },
  { key: "save", label: "Save", number: "02", icon: Folder },
  { key: "matrix", label: "Matrix", number: "03", icon: Table },
  { key: "map", label: "Map", number: "04", icon: Graph },
  { key: "gaps", label: "Gaps", number: "05", icon: Lightbulb },
  { key: "report", label: "Review", number: "06", icon: PencilLine },
];

export const STEP_HREFS: Record<PipelineStepKey, string> = {
  search: "/search",
  save: "/papers",
  matrix: "/matrix",
  map: "/map",
  gaps: "/gaps",
  report: "/reports",
};

export const STEP_NEXT_LABELS: Record<PipelineStepKey, string> = {
  search: "Search papers for this project",
  save: "Review saved papers",
  matrix: "Generate literature matrix",
  map: "Explore knowledge map",
  gaps: "Generate research gaps",
  report: "Generate literature review",
};

interface Props {
  current: number; // 0..6
  compact?: boolean;
}

export function WorkflowPipeline({ current, compact = false }: Props) {
  const clamped = Math.max(0, Math.min(PIPELINE_STEPS.length, current));
  const size = compact ? "h-8 w-8 text-[12px]" : "h-10 w-10 text-[13px]";
  const iconSize = compact ? 14 : 16;
  const labelCls = compact ? "text-[11px]" : "text-[12px]";
  const gapCls = compact ? "gap-1 sm:gap-2" : "gap-1.5 sm:gap-2";
  const barCls = compact ? "w-2 sm:w-4" : "w-3 sm:w-6";

  return (
    <div className={"flex items-center " + gapCls + " overflow-x-auto scrollbar-hide"}>
      {PIPELINE_STEPS.map((s, i) => {
        const isDone = i < clamped;
        const isCurrent = i === clamped;
        const Icon = s.icon;
        return (
          <div key={s.key} className={"flex items-center " + gapCls + " shrink-0"}>
            <div
              className={
                "flex " + size + " items-center justify-center rounded-full font-display font-bold transition-all " +
                (isDone
                  ? "bg-primary text-on-primary"
                  : isCurrent
                    ? "bg-ink text-on-dark ring-4 ring-primary/20"
                    : "bg-surface-bone text-ash")
              }
              aria-current={isCurrent ? "step" : undefined}
            >
              {isDone ? (
                <svg width={iconSize} height={iconSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : (
                <Icon size={iconSize} weight="bold" />
              )}
            </div>
            <span
              className={
                "font-ui " + labelCls + " font-medium " +
                (isCurrent ? "text-ink" : isDone ? "text-charcoal" : "text-ash")
              }
            >
              {s.label}
            </span>
            {i < PIPELINE_STEPS.length - 1 && (
              <span className={"h-px " + barCls + " " + (isDone ? "bg-primary" : "bg-hairline")} />
            )}
          </div>
        );
      })}
    </div>
  );
}
