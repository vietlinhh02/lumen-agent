"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  FileText,
  Sparkle,
  Table,
  Warning,
} from "@phosphor-icons/react";
import { WorkflowPipeline, type PipelineStepKey } from "./WorkflowPipeline";
import type { ProjectWorkflowStatus } from "@/lib/stores/projects-store";
import { relativeTime } from "@/lib/utils";

interface Props {
  workflow: ProjectWorkflowStatus;
}

interface NextAction {
  current: number;
  label: string;
  slug: PipelineStepKey;
  insight: string;
}

function deriveNextAction(workflow: ProjectWorkflowStatus): NextAction {
  if (workflow.paper_count === 0) {
    return {
      current: 0,
      label: "Search papers",
      slug: "search",
      insight: "Start by finding academic papers for this research topic.",
    };
  }
  if (workflow.paper_count < 5) {
    return {
      current: 1,
      label: `Add more papers (${workflow.paper_count}/5)`,
      slug: "search",
      insight: "Save at least 5 papers before generating a defensible matrix.",
    };
  }
  if (workflow.full_text_count < workflow.paper_count) {
    const missing = workflow.paper_count - workflow.full_text_count;
    return {
      current: 2,
      label: "Review saved papers",
      slug: "save",
      insight: `${missing} saved paper${missing === 1 ? "" : "s"} still need full text.`,
    };
  }
  if (workflow.matrix_count < workflow.paper_count) {
    const missing = workflow.paper_count - workflow.matrix_count;
    return {
      current: 2,
      label: "Generate literature matrix",
      slug: "matrix",
      insight: `${missing} paper${missing === 1 ? "" : "s"} are missing matrix rows.`,
    };
  }
  if (workflow.gap_count === 0) {
    return {
      current: 4,
      label: "Detect research gaps",
      slug: "gaps",
      insight: "The matrix is ready. Use it to find evidence-backed gaps.",
    };
  }
  if (workflow.report_count === 0) {
    return {
      current: 5,
      label: "Generate literature review",
      slug: "report",
      insight: `${workflow.gap_count} gap${workflow.gap_count === 1 ? "" : "s"} are ready for synthesis.`,
    };
  }
  return {
    current: 6,
    label: "Open literature review",
    slug: "report",
    insight: "A citation-safe review exists. Review, export, or regenerate sections.",
  };
}

export function ContinueWorkingHero({ workflow }: Props) {
  const next = deriveNextAction(workflow);
  const progress = Math.round((Math.min(next.current, 6) / 6) * 100);
  const projectBase = `/projects/${workflow.id}`;
  // Map pipeline slug to a real route inside the workspace.
  const SLUG_HREFS: Record<PipelineStepKey, string> = {
    search: `${projectBase}/search`,
    save: `${projectBase}/papers`,
    matrix: `${projectBase}/matrix`,
    map: `${projectBase}/map`,
    gaps: `${projectBase}/gaps`,
    report: `${projectBase}/reports`,
  };

  return (
    <section
      className="mb-5 overflow-hidden rounded-[14px] bg-surface-card animate-slide-up sm:mb-8 sm:rounded-[16px]"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="p-4 sm:p-8">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 font-ui text-[11px] font-semibold uppercase tracking-wider text-primary">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
            Active Project
          </span>
          <span className="font-ui text-[12px] text-ash">
            · Updated {relativeTime(workflow.updated_at)}
          </span>
        </div>

        <h2
          className="font-display text-[24px] font-bold leading-[1.05] text-ink sm:text-[32px]"
        >
          {workflow.title}
        </h2>
        {workflow.topic && (
          <p className="mt-1.5 line-clamp-2 text-sm leading-[1.5] text-charcoal sm:line-clamp-1">
            {workflow.topic}
          </p>
        )}

        <div className="mt-5 sm:mt-6">
          <WorkflowPipeline current={next.current} compact />
        </div>

        <div className="mt-4 flex items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-bone">
            <div
              className="h-full rounded-full bg-primary transition-all duration-700"
              style={{ width: progress + "%" }}
            />
          </div>
          <span className="font-ui shrink-0 text-[11px] font-semibold text-charcoal">
            {progress}%
          </span>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="rounded-[10px] bg-surface-bone px-3 py-2.5">
              <div className="flex items-center gap-1.5 font-ui text-[11px] text-ash">
                <FileText size={13} weight="bold" />
                Corpus
              </div>
              <p className="mt-1 font-ui text-[13px] font-semibold text-ink">
                {workflow.paper_count} saved · {workflow.full_text_count} text-ready
              </p>
            </div>
            <div className="rounded-[10px] bg-surface-bone px-3 py-2.5">
              <div className="flex items-center gap-1.5 font-ui text-[11px] text-ash">
                <Table size={13} weight="bold" />
                Analysis
              </div>
              <p className="mt-1 font-ui text-[13px] font-semibold text-ink">
                {workflow.matrix_count} matrix · {workflow.gap_count} gaps
              </p>
            </div>
            <div className="rounded-[10px] bg-surface-bone px-3 py-2.5">
              <div className="flex items-center gap-1.5 font-ui text-[11px] text-ash">
                {workflow.conflict_count > 0 ? (
                  <Warning size={13} weight="bold" />
                ) : (
                  <CheckCircle size={13} weight="bold" />
                )}
                Review
              </div>
              <p className="mt-1 font-ui text-[13px] font-semibold text-ink">
                {workflow.conflict_count} conflicts · {workflow.report_count} reports
              </p>
            </div>
          </div>
          <div className="grid gap-3 sm:flex sm:flex-wrap sm:items-center lg:justify-end">
            <p className="font-ui text-[12px] leading-[1.5] text-charcoal sm:w-full lg:w-72">
              {next.insight}
            </p>
            <Link
              href={SLUG_HREFS[next.slug]}
              className="focus-ring inline-flex h-11 w-full items-center justify-center gap-2 rounded-full bg-primary px-5 font-ui text-sm font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-[0.98] sm:w-auto"
            >
              <Sparkle size={16} weight="fill" />
              {next.label}
              <ArrowRight size={14} weight="bold" />
            </Link>
            <Link
              href={projectBase}
              className="font-ui inline-flex h-11 w-full items-center justify-center gap-2 rounded-full bg-surface-bone px-5 text-sm font-semibold text-ink transition-colors hover:bg-hairline active:scale-[0.98] sm:w-auto"
            >
              Open Workspace
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
