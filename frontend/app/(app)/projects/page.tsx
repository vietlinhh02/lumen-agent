"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { Plus, Folder, Sparkle, Clock, Article } from "@phosphor-icons/react";
import { useAuth } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import type { ProjectResponse } from "@/lib/types";
import { relativeTime } from "@/lib/utils";

function paperLabel(count: number) {
  if (count === 0) return "No papers";
  if (count === 1) return "1 paper";
  return `${count} papers`;
}

function ProjectCard({ project, index }: { project: ProjectResponse; index: number }) {
  const hasPapers = project.paper_count > 0;

  return (
    <a
      href={`/projects/${project.id}`}
      className="group block rounded-[14px] bg-surface-card p-6 transition-all duration-200 animate-scale-in"
      style={{
        border: "1px solid var(--hairline)",
        animationDelay: `${index * 60}ms`,
      }}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <h2 className="font-ui text-[18px] font-semibold leading-[1.3] text-ink group-hover:text-primary transition-colors duration-200 line-clamp-2">
          {project.title}
        </h2>
        <span
          className={`font-ui shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold leading-[1.4] ${
            project.status === "active"
              ? "bg-green-50 text-green-700"
              : "bg-ash/10 text-ash"
          }`}
        >
          {project.status === "active" ? "Active" : "Archived"}
        </span>
      </div>

      {project.topic && (
        <p className="text-sm leading-[1.5] text-charcoal line-clamp-1">
          {project.topic}
        </p>
      )}

      {project.research_question && (
        <p className="mt-2 text-[13px] leading-[1.6] text-mute line-clamp-2">
          {project.research_question}
        </p>
      )}

      <div className="mt-5 flex items-center gap-3">
        {hasPapers && (
          <span className="font-ui inline-flex items-center gap-1 rounded-full bg-surface-bone px-2.5 py-0.5 text-[11px] font-medium text-charcoal">
            <Article size={11} weight="fill" />
            {paperLabel(project.paper_count)}
          </span>
        )}
        <span className="font-ui inline-flex items-center gap-1.5 text-[12px] text-ash">
          <Clock size={12} />
          {relativeTime(project.updated_at)}
        </span>
      </div>
    </a>
  );
}

function SkeletonCard({ index }: { index: number }) {
  return (
    <div
      className="rounded-[14px] bg-surface-card p-6 animate-pulse"
      style={{
        border: "1px solid var(--hairline)",
        animationDelay: `${index * 60}ms`,
      }}
    >
      <div className="flex justify-between mb-3">
        <div className="h-5 w-3/4 rounded bg-surface-bone" />
        <div className="h-5 w-14 rounded-full bg-surface-bone" />
      </div>
      <div className="h-4 w-1/2 rounded bg-surface-bone" />
      <div className="mt-2 h-4 w-5/6 rounded bg-surface-bone" />
      <div className="mt-5 flex gap-3">
        <div className="h-5 w-20 rounded-full bg-surface-bone" />
        <div className="h-3 w-24 rounded bg-surface-bone" />
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  const token = useAuth((s) => s.token);
  const router = useRouter();
  const projects = useProjectsStore((s) => s.projects);
  const loading = useProjectsStore((s) => s.loading);
  const filter = useProjectsStore((s) => s.filter);
  const setFilter = useProjectsStore((s) => s.setFilter);
  const fetchProjects = useProjectsStore((s) => s.fetchProjects);

  useEffect(() => {
    if (token) void fetchProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const filtered = useMemo(
    () => (filter === "all" ? projects : projects.filter((p) => p.status === filter)),
    [projects, filter],
  );

  const activeCount = projects.filter((p) => p.status === "active").length;
  const archivedCount = projects.filter((p) => p.status === "archived").length;

  return (
    <div className="animate-fade-in">
      <div className="mb-10">
        <div className="flex items-end justify-between">
          <div>
            <h1
              className="font-display text-[40px] font-bold leading-[1.0] text-ink"
              style={{ letterSpacing: "-1px" }}
            >
              Projects
            </h1>
            <p className="mt-2 max-w-lg text-base leading-[1.6] text-charcoal">
              Organize your literature reviews. Each project holds its own collection of papers, notes, and analysis.
            </p>
          </div>

          <button
            onClick={() => router.push("/projects/new")}
            className="focus-ring font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-95"
          >
            <Plus size={18} weight="bold" />
            New Project
          </button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <SkeletonCard key={i} index={i} />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center animate-slide-up">
          <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-surface-bone">
            <Folder size={36} className="text-stone" weight="light" />
          </div>
          <h2
            className="font-display text-[24px] font-bold leading-[1.2] text-ink"
            style={{ letterSpacing: "-0.5px" }}
          >
            No projects yet
          </h2>
          <p className="mt-3 max-w-sm text-base leading-[1.6] text-charcoal">
            Create your first research project to start organizing papers, building matrices, and discovering knowledge gaps.
          </p>
          <button
            onClick={() => router.push("/projects/new")}
            className="focus-ring font-ui mt-8 inline-flex items-center gap-2 h-[48px] rounded-full bg-primary px-6 text-base font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-95"
          >
            <Sparkle size={20} weight="fill" />
            Create Your First Project
          </button>
        </div>
      ) : (
        <>
          <div className="mb-6 flex items-center gap-1">
            {[
              { key: "all", label: "All", count: projects.length },
              { key: "active", label: "Active", count: activeCount },
              { key: "archived", label: "Archived", count: archivedCount },
            ].map(({ key, label, count }) => (
              <button
                key={key}
                onClick={() => setFilter(key as typeof filter)}
                className={`font-ui rounded-full px-4 py-1.5 text-[13px] font-semibold transition-all duration-200 ${
                  filter === key
                    ? "bg-ink text-on-dark"
                    : "text-charcoal hover:text-ink hover:bg-surface-bone"
                }`}
              >
                {label}
                <span className={`ml-1.5 ${filter === key ? "opacity-70" : "opacity-50"}`}>
                  {count}
                </span>
              </button>
            ))}
          </div>

          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center animate-slide-up">
              <p className="font-ui text-base font-semibold text-ink">No {filter} projects</p>
              <p className="mt-1 text-sm text-charcoal">
                {filter === "archived"
                  ? "Archive a project to see it here."
                  : "All your active projects are shown here."}
              </p>
            </div>
          ) : (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((project, i) => (
                <ProjectCard key={project.id} project={project} index={i} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
