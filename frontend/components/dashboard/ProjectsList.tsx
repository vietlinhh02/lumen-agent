"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  FileText,
  Folder,
  Lightbulb,
  MagnifyingGlass,
  PencilLine,
  Table,
} from "@phosphor-icons/react";
import type { ProjectResponse } from "@/lib/types";
import type { ProjectWorkflowStatus } from "@/lib/stores/projects-store";

interface ProjectAction {
  label: string;
  href: string;
  progress: number;
  icon: typeof MagnifyingGlass;
  hint: string;
}

function fallbackWorkflow(project: ProjectResponse): ProjectWorkflowStatus {
  return {
    id: project.id,
    title: project.title,
    topic: project.topic,
    status: project.status,
    updated_at: project.updated_at,
    paper_count: project.paper_count,
    full_text_count: 0,
    raw_text_count: 0,
    matrix_count: 0,
    gap_count: 0,
    conflict_count: 0,
    report_count: 0,
  };
}

function projectAction(workflow: ProjectWorkflowStatus): ProjectAction {
  const base = `/projects/${workflow.id}`;
  if (workflow.paper_count === 0) {
    return {
      label: "Search papers",
      href: `${base}/search`,
      progress: 4,
      icon: MagnifyingGlass,
      hint: "No corpus yet",
    };
  }
  if (workflow.paper_count < 5) {
    return {
      label: "Add more papers",
      href: `${base}/search`,
      progress: 18,
      icon: FileText,
      hint: `${workflow.paper_count}/5 papers saved`,
    };
  }
  if (workflow.matrix_count < workflow.paper_count) {
    return {
      label: "Generate matrix",
      href: `${base}/matrix`,
      progress: 42,
      icon: Table,
      hint: `${workflow.paper_count - workflow.matrix_count} rows missing`,
    };
  }
  if (workflow.gap_count === 0) {
    return {
      label: "Detect gaps",
      href: `${base}/gaps`,
      progress: 68,
      icon: Lightbulb,
      hint: "Matrix ready",
    };
  }
  if (workflow.report_count === 0) {
    return {
      label: "Generate review",
      href: `${base}/reports`,
      progress: 84,
      icon: PencilLine,
      hint: `${workflow.gap_count} gaps found`,
    };
  }
  return {
    label: "Open review",
    href: `${base}/reports`,
    progress: 100,
    icon: CheckCircle,
    hint: "Review ready",
  };
}

interface Props {
  projects: ProjectResponse[];
  workflows?: ProjectWorkflowStatus[];
  loading?: boolean;
}

export function ProjectsList({ projects, workflows = [], loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-32 rounded-[12px] bg-surface-card animate-pulse sm:h-24"
            style={{ border: "1px solid var(--hairline)" }}
          />
        ))}
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-[12px] px-4 py-10 text-center sm:py-12"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-surface-bone">
          <Folder size={28} className="text-stone" />
        </div>
        <p className="font-ui text-sm font-semibold text-ink">No projects yet</p>
        <Link
          href="/projects/new"
          className="mt-4 inline-flex h-10 items-center gap-2 rounded-full bg-primary px-5 font-ui text-[13px] font-semibold text-on-primary hover:bg-primary-deep transition-colors"
        >
          Create your first project
        </Link>
      </div>
    );
  }

  const workflowsById = new Map(workflows.map((workflow) => [workflow.id, workflow]));

  return (
    <div className="space-y-3">
      {projects.slice(0, 5).map((p) => {
        const workflow = workflowsById.get(p.id) ?? fallbackWorkflow(p);
        const action = projectAction(workflow);
        const ActionIcon = action.icon;
        return (
          <div
            key={p.id}
            className="group rounded-[12px] bg-surface-card p-3 transition-all hover:shadow-sm sm:p-4"
            style={{ border: "1px solid var(--hairline)" }}
          >
            <div className="flex items-start gap-3 sm:gap-4">
              <Link
                href={"/projects/" + p.id}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] bg-primary/10 sm:h-10 sm:w-10 sm:rounded-[10px]"
              >
                <Folder size={17} className="text-primary" weight="fill" />
              </Link>
              <div className="min-w-0 flex-1">
                <div className="mb-2 grid gap-1 sm:flex sm:items-center sm:justify-between sm:gap-2">
                  <Link
                    href={"/projects/" + p.id}
                    className="font-ui line-clamp-2 text-[14px] font-semibold leading-snug text-ink transition-colors hover:text-primary sm:truncate"
                  >
                    {p.title}
                  </Link>
                  <span className={
                    "font-ui w-fit shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold " +
                    (p.status === "active" ? "bg-green-50 text-green-700" : "bg-ash/10 text-ash")
                  }>
                    {p.status === "active" ? "Active" : "Archived"}
                  </span>
                </div>
                <div className="grid gap-2 md:grid-cols-[1fr_auto] md:items-center">
                  <div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-surface-bone">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: action.progress + "%" }}
                      />
                    </div>
                    <p className="mt-1.5 font-ui text-[11px] leading-snug text-ash">
                      {workflow.paper_count} papers · {workflow.matrix_count} matrix ·{" "}
                      {workflow.gap_count} gaps · {workflow.report_count} reports
                    </p>
                  </div>
                  <Link
                    href={action.href}
                    className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-full bg-surface-bone px-3 font-ui text-[11px] font-semibold text-ink transition-colors hover:bg-hairline md:h-8 md:w-auto"
                  >
                    <ActionIcon size={12} weight="bold" />
                    {action.label}
                    <ArrowRight size={11} weight="bold" />
                  </Link>
                </div>
              </div>
            </div>
            <p className="mt-3 rounded-[8px] bg-surface-bone px-3 py-2 font-ui text-[11px] leading-snug text-charcoal">
              {action.hint}
            </p>
          </div>
        );
      })}
      {projects.length > 5 && (
        <Link
          href="/projects"
          className="flex items-center justify-center gap-1.5 rounded-[12px] py-2.5 font-ui text-[13px] font-medium text-charcoal hover:text-ink hover:bg-surface-bone transition-colors"
          style={{ border: "1px solid var(--hairline)" }}
        >
          View all {projects.length} projects <ArrowRight size={13} />
        </Link>
      )}
    </div>
  );
}
