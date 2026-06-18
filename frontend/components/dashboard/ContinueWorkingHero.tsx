"use client";

import Link from "next/link";
import { ArrowRight, Sparkle } from "@phosphor-icons/react";
import { WorkflowPipeline, STEP_HREFS, type PipelineStepKey } from "./WorkflowPipeline";
import type { ProjectResponse } from "@/lib/types";
import type { StatsData } from "@/lib/stores/projects-store";
import { relativeTime } from "@/lib/utils";

interface Props {
  project: ProjectResponse;
  stats: StatsData;
}

function deriveStep(stats: StatsData): number {
  if (stats.report_count > 0) return 6;
  if (stats.gap_count > 0) return 5;
  if (stats.matrix_count > 0) return 4;
  if (stats.paper_count >= 5) return 3;
  if (stats.paper_count > 0) return 2;
  return 1;
}

const NEXT: Record<number, { key: PipelineStepKey; label: string }> = {
  1: { key: "save",   label: "Add more papers" },
  2: { key: "matrix", label: "Generate literature matrix" },
  3: { key: "map",    label: "Explore knowledge map" },
  4: { key: "gaps",   label: "Generate research gaps" },
  5: { key: "report", label: "Generate literature review" },
  6: { key: "report", label: "View your review" },
};

export function ContinueWorkingHero({ project, stats }: Props) {
  const step = deriveStep(stats);
  const next = NEXT[step];
  const progress = Math.round(((step - 1) / 5) * 100);

  return (
    <section
      className="mb-8 overflow-hidden rounded-[16px] bg-surface-card animate-slide-up"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="p-6 sm:p-8">
        <div className="mb-3 flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 font-ui text-[11px] font-semibold uppercase tracking-wider text-primary">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
            Active Project
          </span>
          <span className="font-ui text-[12px] text-ash">
            · Updated {relativeTime(project.updated_at)}
          </span>
        </div>

        <h2
          className="font-display text-[28px] font-bold leading-[1.0] text-ink sm:text-[32px]"
          style={{ letterSpacing: "-0.5px" }}
        >
          {project.title}
        </h2>
        {project.topic && (
          <p className="mt-1.5 line-clamp-1 text-sm leading-[1.5] text-charcoal">{project.topic}</p>
        )}

        <div className="mt-6">
          <WorkflowPipeline current={step} />
        </div>

        <div className="mt-4 flex items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-bone">
            <div
              className="h-full rounded-full bg-primary transition-all duration-700"
              style={{ width: progress + "%" }}
            />
          </div>
          <span className="font-ui shrink-0 text-[11px] font-semibold text-charcoal">{progress}%</span>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Link
            href={STEP_HREFS[next.key] + "?project=" + project.id}
            className="focus-ring inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 font-ui text-sm font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-[0.98]"
          >
            <Sparkle size={16} weight="fill" />
            {next.label}
            <ArrowRight size={14} weight="bold" />
          </Link>
          <Link
            href={"/projects/" + project.id}
            className="font-ui inline-flex h-11 items-center gap-2 rounded-full bg-surface-bone px-5 text-sm font-semibold text-ink transition-colors hover:bg-hairline active:scale-[0.98]"
          >
            View Project
          </Link>
        </div>
      </div>
    </section>
  );
}
