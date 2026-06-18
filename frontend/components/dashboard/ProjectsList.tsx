"use client";

import Link from "next/link";
import { Folder, ArrowRight } from "@phosphor-icons/react";
import type { ProjectResponse } from "@/lib/types";

function projectProgress(p: ProjectResponse): number {
  if (p.paper_count === 0) return 5;
  if (p.paper_count < 5) return 20;
  if (p.paper_count < 20) return 40;
  return 60;
}

function stepHint(p: ProjectResponse): string {
  if (p.paper_count === 0) return "Just started";
  if (p.paper_count < 5) return p.paper_count + " paper" + (p.paper_count !== 1 ? "s" : "") + " saved";
  return "Ready for analysis";
}

interface Props {
  projects: ProjectResponse[];
  loading?: boolean;
}

export function ProjectsList({ projects, loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-[12px] bg-surface-card animate-pulse" style={{ border: "1px solid var(--hairline)" }} />
        ))}
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-[12px] py-12 text-center" style={{ border: "1px solid var(--hairline)" }}>
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
    <div className="space-y-3">
      {projects.slice(0, 5).map((p) => {
        const progress = projectProgress(p);
        const hint = stepHint(p);
        return (
          <Link
            key={p.id}
            href={"/projects/" + p.id}
            className="group flex items-center gap-4 rounded-[12px] bg-surface-card p-4 transition-all hover:shadow-sm"
            style={{ border: "1px solid var(--hairline)" }}
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-primary/10">
              <Folder size={18} className="text-primary" weight="fill" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <h3 className="font-ui truncate text-[14px] font-semibold text-ink transition-colors group-hover:text-primary">
                  {p.title}
                </h3>
                <span className={
                  "font-ui shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold " +
                  (p.status === "active" ? "bg-green-50 text-green-700" : "bg-ash/10 text-ash")
                }>
                  {p.status === "active" ? "Active" : "Archived"}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-surface-bone">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: progress + "%" }}
                  />
                </div>
                <span className="font-ui shrink-0 text-[11px] text-ash">
                  {p.paper_count} paper{p.paper_count !== 1 ? "s" : ""}
                </span>
              </div>
            </div>
            <ArrowRight size={14} className="shrink-0 text-stone transition-colors group-hover:text-ink" />
          </Link>
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
