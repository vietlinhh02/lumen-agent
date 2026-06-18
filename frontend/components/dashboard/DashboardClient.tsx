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
import { GlobalSearchBar } from "./GlobalSearchBar";

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

  // Active project = most recently updated with status=active
  const activeProject = useMemo(() => {
    return projects.find((p) => p.status === "active") ?? projects[0] ?? null;
  }, [projects]);

  return (
    <div>
      <DashboardHeader stats={stats} runningJobs={0} />

      <GlobalSearchBar />

      {activeProject && stats && (
        <ContinueWorkingHero project={activeProject} stats={stats} />
      )}

      <StatsGrid stats={stats} />

      <QuickActionsRow projectCount={stats?.project_count ?? 0} />

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <h2 className="mb-4 font-ui text-[12px] font-semibold uppercase tracking-wider text-ash">
            Your Projects
          </h2>
          <ProjectsList projects={projects} loading={loadingProjects} />
        </section>

        <section>
          <h2 className="mb-4 font-ui text-[12px] font-semibold uppercase tracking-wider text-ash">
            Activity & Insights
          </h2>
          <ActivityFeed stats={stats} />
        </section>
      </div>
    </div>
  );
}
