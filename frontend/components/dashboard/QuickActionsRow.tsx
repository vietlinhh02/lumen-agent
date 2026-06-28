"use client";

import Link from "next/link";
import {
  MagnifyingGlass,
  Table,
  Lightbulb,
  PencilLine,
  ArrowRight,
  Folder,
} from "@phosphor-icons/react";
import { useProjectsStore } from "@/lib/stores/projects-store";

const ACTIONS = [
  {
    slug: "search",
    label: "Search Papers",
    sub: "Find & save papers",
    icon: MagnifyingGlass,
    color: "bg-primary/10 text-primary",
  },
  {
    slug: "matrix",
    label: "Matrix",
    sub: "Compare papers",
    icon: Table,
    color: "bg-amber-50 text-amber-600",
  },
  {
    slug: "gaps",
    label: "Gaps",
    sub: "Find research gaps",
    icon: Lightbulb,
    color: "bg-violet-50 text-violet-600",
  },
  {
    slug: "reports",
    label: "Review",
    sub: "Export citation-safe review",
    icon: PencilLine,
    color: "bg-emerald-50 text-emerald-600",
  },
];

interface Props {
  projectCount: number;
}

export function QuickActionsRow({ projectCount }: Props) {
  // Quick Actions now route into the most-recent active project's
  // workspace tab. If the user has no projects yet, the buttons are
  // disabled and link to the create-project flow.
  const projects = useProjectsStore((s) => s.projects);
  const activeProjectId =
    projects.find((p) => p.status === "active")?.id ?? projects[0]?.id ?? null;

  return (
    <div data-tour="quick-actions" className="mb-5 animate-slide-up delay-100 sm:mb-8">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-ui text-[12px] font-semibold uppercase tracking-wider text-ash">
          Quick Actions
        </h2>
        {projectCount > 0 && (
          <Link
            href="/projects/new"
            className="font-ui inline-flex items-center gap-1.5 text-[12px] font-medium text-primary hover:text-primary-deep transition-colors"
          >
            New Project <ArrowRight size={12} weight="bold" />
          </Link>
        )}
      </div>
      {projectCount === 0 ? (
        <Link
          href="/projects/new"
          className="flex items-center gap-3 rounded-[12px] bg-surface-card p-4 transition-all hover:shadow-sm"
          style={{ border: "1px solid var(--hairline)" }}
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-primary/10 text-primary">
            <Folder size={18} weight="bold" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-ui text-[13px] font-semibold text-ink">Create your first project</p>
            <p className="font-ui text-[11px] text-ash">Then explore the full workspace</p>
          </div>
          <ArrowRight size={14} className="shrink-0 text-stone" />
        </Link>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-4">
          {ACTIONS.map((a) => {
            const href = activeProjectId ? `/projects/${activeProjectId}/${a.slug}` : "/projects/new";
            return (
              <Link
                key={a.slug}
                href={href}
                className="group flex min-h-14 items-center gap-3 rounded-[12px] bg-surface-card p-3 transition-all hover:shadow-sm active:scale-[0.98] sm:p-4"
                style={{ border: "1px solid var(--hairline)" }}
              >
                <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] sm:h-10 sm:w-10 sm:rounded-[10px] ${a.color}`}>
                  <a.icon size={17} weight="bold" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-ui text-[13px] font-semibold text-ink">{a.label}</p>
                  <p className="font-ui text-[11px] leading-tight text-ash">{a.sub}</p>
                </div>
                <ArrowRight
                  size={14}
                  className="shrink-0 text-stone transition-colors group-hover:text-ink"
                />
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
