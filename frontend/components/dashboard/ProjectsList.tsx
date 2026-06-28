"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  FileText,
  Folder,
  Lightbulb,
  List,
  MagnifyingGlass,
  PencilLine,
  SquaresFour,
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

const TOPIC_PALETTES = [
  { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200", dot: "bg-amber-500" },
  { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", dot: "bg-emerald-500" },
  { bg: "bg-violet-50", text: "text-violet-700", border: "border-violet-200", dot: "bg-violet-500" },
  { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200", dot: "bg-blue-500" },
  { bg: "bg-rose-50", text: "text-rose-700", border: "border-rose-200", dot: "bg-rose-500" },
  { bg: "bg-cyan-50", text: "text-cyan-700", border: "border-cyan-200", dot: "bg-cyan-500" },
  { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200", dot: "bg-orange-500" },
  { bg: "bg-lime-50", text: "text-lime-700", border: "border-lime-200", dot: "bg-lime-500" },
  { bg: "bg-indigo-50", text: "text-indigo-700", border: "border-indigo-200", dot: "bg-indigo-500" },
  { bg: "bg-pink-50", text: "text-pink-700", border: "border-pink-200", dot: "bg-pink-500" },
];

function normalizeTopic(topic: string | null | undefined): string {
  if (!topic || topic.trim() === "") return "Uncategorized";
  return topic.trim();
}

function topicPalette(topic: string) {
  let hash = 0;
  for (let i = 0; i < topic.length; i++) {
    hash = topic.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % TOPIC_PALETTES.length;
  return TOPIC_PALETTES[index];
}

interface ProjectCardProps {
  project: ProjectResponse;
  workflow: ProjectWorkflowStatus;
}

function ProjectCard({ project, workflow }: ProjectCardProps) {
  const action = projectAction(workflow);
  const ActionIcon = action.icon;
  return (
    <div
      className="group rounded-[12px] bg-surface-card p-3 transition-all hover:shadow-sm sm:p-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="flex items-start gap-3 sm:gap-4">
        <Link
          href={"/projects/" + project.id}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] bg-primary/10 sm:h-10 sm:w-10 sm:rounded-[10px]"
        >
          <Folder size={17} className="text-primary" weight="fill" />
        </Link>
        <div className="min-w-0 flex-1">
          <div className="mb-2 grid gap-1 sm:flex sm:items-center sm:justify-between sm:gap-2">
            <Link
              href={"/projects/" + project.id}
              className="font-ui line-clamp-2 text-[14px] font-semibold leading-snug text-ink transition-colors hover:text-primary sm:truncate"
            >
              {project.title}
            </Link>
            <span
              className={
                "font-ui w-fit shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold " +
                (project.status === "active"
                  ? "bg-green-50 text-green-700"
                  : "bg-ash/10 text-ash")
              }
            >
              {project.status === "active" ? "Active" : "Archived"}
            </span>
          </div>
          <div className="grid gap-2">
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
              className="inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-full bg-surface-bone px-3 font-ui text-[11px] font-semibold text-ink transition-colors hover:bg-hairline"
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
}

interface Props {
  projects: ProjectResponse[];
  workflows?: ProjectWorkflowStatus[];
  loading?: boolean;
}

type ViewMode = "list" | "category";

export function ProjectsList({ projects, workflows = [], loading }: Props) {
  const [viewMode, setViewMode] = useState<ViewMode>("list");

  const workflowsById = useMemo(
    () => new Map(workflows.map((workflow) => [workflow.id, workflow])),
    [workflows],
  );

  const projectsWithWorkflows = useMemo(() => {
    return projects.map((p) => ({
      project: p,
      workflow: workflowsById.get(p.id) ?? fallbackWorkflow(p),
    }));
  }, [projects, workflowsById]);

  const groupedByTopic = useMemo(() => {
    const map = new Map<string, typeof projectsWithWorkflows>();
    for (const item of projectsWithWorkflows) {
      const key = normalizeTopic(item.project.topic);
      const group = map.get(key) ?? [];
      group.push(item);
      map.set(key, group);
    }
    // Sort groups by project count (largest first), then alphabetically.
    return Array.from(map.entries())
      .map(([topic, items]) => ({ topic, items }))
      .sort((a, b) => {
        if (b.items.length !== a.items.length) return b.items.length - a.items.length;
        return a.topic.localeCompare(b.topic);
      });
  }, [projectsWithWorkflows]);

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

  return (
    <div data-tour="projects-list" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-ui text-[12px] text-ash">
          {projects.length} project{projects.length !== 1 ? "s" : ""}
          {viewMode === "category" && (
            <>
              {" "}
              · {groupedByTopic.length} categor{groupedByTopic.length !== 1 ? "ies" : "y"}
            </>
          )}
        </p>
        <div
          className="inline-flex rounded-full border border-hairline bg-surface-card p-0.5"
          role="group"
          aria-label="Project view mode"
        >
          <button
            type="button"
            onClick={() => setViewMode("list")}
            aria-pressed={viewMode === "list"}
            className={
              "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 font-ui text-[11px] font-medium transition-colors " +
              (viewMode === "list"
                ? "bg-primary text-on-primary"
                : "text-charcoal hover:text-ink hover:bg-surface-bone")
            }
          >
            <List size={13} weight="bold" />
            List
          </button>
          <button
            type="button"
            onClick={() => setViewMode("category")}
            aria-pressed={viewMode === "category"}
            className={
              "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 font-ui text-[11px] font-medium transition-colors " +
              (viewMode === "category"
                ? "bg-primary text-on-primary"
                : "text-charcoal hover:text-ink hover:bg-surface-bone")
            }
          >
            <SquaresFour size={13} weight="bold" />
            Category
          </button>
        </div>
      </div>

      {viewMode === "list" ? (
        <div className="space-y-3">
          <div
            className="grid gap-3"
            style={{
              gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))",
            }}
          >
            {projectsWithWorkflows.slice(0, 5).map(({ project, workflow }) => (
              <ProjectCard key={project.id} project={project} workflow={workflow} />
            ))}
          </div>
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
      ) : (
        <div className="space-y-6">
          <div
            className="grid items-start gap-6"
            style={{
              gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))",
            }}
          >
            {groupedByTopic.map(({ topic, items }) => {
              const palette = topicPalette(topic);
              return (
                <section key={topic} className="animate-fade-in-up flex flex-col gap-3">
                  <div
                    className={`flex w-fit max-w-full min-w-0 items-center gap-2 rounded-full border px-3 py-1.5 font-ui text-[11px] font-semibold ${palette.bg} ${palette.text} ${palette.border}`}
                    title={topic}
                  >
                    <span className={`h-2 w-2 shrink-0 rounded-full ${palette.dot}`} />
                    <span className="min-w-0 truncate">{topic}</span>
                    <span className="shrink-0 rounded-full bg-white/60 px-1.5 py-0.5 text-[10px]">
                      {items.length}
                    </span>
                  </div>
                  <div className="flex flex-col gap-3">
                    {items.map(({ project, workflow }) => (
                      <ProjectCard key={project.id} project={project} workflow={workflow} />
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
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
      )}
    </div>
  );
}
