"use client";

import { useEffect, useMemo } from "react";
import { useAuth } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { DashboardHeader } from "./DashboardHeader";
import { ContinueWorkingHero } from "./ContinueWorkingHero";
import { QuickActionsRow } from "./QuickActionsRow";
import { StatsGrid } from "./StatsGrid";
import { ProjectsList } from "./ProjectsList";
import { ActivityFeed } from "./ActivityFeed";

export function DashboardClient() {
  const token = useAuth((s) => s.token);
  const stats = useProjectsStore((s) => s.stats);
  const projects = useProjectsStore((s) => s.projects);
  const loadingProjects = useProjectsStore((s) => s.loading);
  const fetchStats = useProjectsStore((s) => s.fetchStats);
  const fetchProjects = useProjectsStore((s) => s.fetchProjects);

  useEffect(() => {
    if (token) {
      void fetchStats();
      void fetchProjects();
    }
  }, [token, fetchStats, fetchProjects]);

  const activeProject = useMemo(() => {
    return projects.find((p) => p.status === "active") ?? projects[0] ?? null;
  }, [projects]);
  const workflows = useMemo(() => stats?.project_workflows ?? [], [stats?.project_workflows]);
  const activeWorkflow = useMemo(() => {
    if (workflows.length === 0) return null;
    if (!activeProject) return workflows[0] ?? null;
    return workflows.find((workflow) => workflow.id === activeProject.id) ?? workflows[0] ?? null;
  }, [activeProject, workflows]);

  return (
    <div>
      <div className="mb-5 grid gap-4 sm:mb-8 lg:grid-cols-[1fr_auto] lg:items-start">
        <DashboardHeader stats={stats} runningJobs={0} />
        <StatsGrid stats={stats} />
      </div>

      <section className="mb-5 sm:mb-8">
        <h2 className="mb-4 font-ui text-[12px] font-semibold uppercase tracking-wider text-ash">
          Your Projects
        </h2>
        <ProjectsList
          projects={projects}
          workflows={workflows}
          loading={loadingProjects}
        />
      </section>

      {activeWorkflow && (
        <ContinueWorkingHero workflow={activeWorkflow} />
      )}

      <QuickActionsRow projectCount={stats?.project_count ?? 0} />

      <section className="mt-5 sm:mt-8">
        <h2 className="mb-4 font-ui text-[12px] font-semibold uppercase tracking-wider text-ash">
          Activity & Insights
        </h2>
        <ActivityFeed stats={stats} />
      </section>
    </div>
  );
}
