"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { useMatrixStore } from "@/lib/stores/matrix-store";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import {
  MatrixHeader,
  ProjectSelector,
  MatrixTable,
  MatrixEmptyState,
  MatrixStats,
} from "@/components/matrix";

export default function MatrixPage() {
  const token = useAuth((s) => s.token);
  const projects = useProjectsStore((s) => s.projects);
  const fetchProjects = useProjectsStore((s) => s.fetchProjects);
  const selectedProjectId = useMatrixStore((s) => s.selectedProjectId);
  const setSelectedProjectId = useMatrixStore((s) => s.setSelectedProjectId);
  const rows = useMatrixStore((s) => s.rows);
  const loading = useMatrixStore((s) => s.loading);
  const generating = useMatrixStore((s) => s.generating);
  const fetchRows = useMatrixStore((s) => s.fetchRows);
  const generate = useMatrixStore((s) => s.generate);
  const editRow = useMatrixStore((s) => s.editRow);
  const deleteRow = useMatrixStore((s) => s.deleteRow);

  const { poll: pollMatrixJob } = useJobPolling({
    onSuccess: (result) =>
      `Generated ${(result.created_count as number) ?? 0} rows (${(result.skipped_count as number) ?? 0} skipped)`,
    onProgress: (progress, total) => `Processed ${progress}/${total} papers...`,
  });

  // Load projects
  useEffect(() => {
    if (token) {
      void fetchProjects();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Auto-select first project if only one
  useEffect(() => {
    if (projects.length === 1 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects]);

  // Load matrix rows when project changes
  useEffect(() => {
    if (selectedProjectId) {
      void fetchRows(selectedProjectId).catch(() =>
        toast.error("Failed to load matrix"),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  async function handleGenerate() {
    if (!selectedProjectId) return;
    try {
      await generate(selectedProjectId, async (jobId) => {
        await pollMatrixJob(jobId);
        return null;
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    }
  }

  async function handleEdit(rowId: string, field: string, value: string) {
    if (!selectedProjectId) return;
    const updated = await editRow(selectedProjectId, rowId, field, value);
    if (updated) toast.success("Cell updated");
    else toast.error("Update failed");
  }

  async function handleDelete(rowId: string) {
    if (!selectedProjectId) return;
    if (!confirm("Delete this matrix row?")) return;
    const ok = await deleteRow(selectedProjectId, rowId);
    if (ok) toast.success("Row deleted");
    else toast.error("Delete failed");
  }

  return (
    <div className="min-h-screen bg-canvas">
      <div className="px-4 sm:px-6 py-6">
        <div className="flex flex-col gap-6">
          <MatrixHeader
            projectSelected={!!selectedProjectId}
            generating={generating}
            onGenerate={handleGenerate}
          />

          <ProjectSelector
            projects={projects}
            selectedId={selectedProjectId}
            onChange={setSelectedProjectId}
          />

          {loading || !selectedProjectId || rows.length === 0 ? (
            <MatrixEmptyState
              loading={loading}
              hasProject={!!selectedProjectId}
              hasRows={rows.length > 0}
              onGenerate={handleGenerate}
            />
          ) : (
            <MatrixTable
              rows={rows}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          )}

          <MatrixStats rows={rows} />
        </div>
      </div>
    </div>
  );
}
