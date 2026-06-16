import { useProjectsStore } from "@/lib/stores/projects-store";
import type { ProjectResponse } from "@/lib/types";

/**
 * Read-only convenience hook for accessing the projects list from the
 * global store. It does NOT trigger a fetch – the projects list is
 * pre-fetched centrally in `AppLayout` when the user is authenticated.
 *
 * If you need to force a fresh fetch, use `useProjectsStore` directly:
 *
 *   useProjectsStore.getState().fetchProjects({ force: true })
 */
export function useProjects(): {
  projects: ProjectResponse[];
  loading: boolean;
} {
  const projects = useProjectsStore((s) => s.projects);
  const loading = useProjectsStore((s) => s.loading);
  return { projects, loading };
}
