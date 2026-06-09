"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type {
  MatrixRowResponse,
  MatrixListResponse,
  MatrixGenerateResponse,
  ProjectListResponse,
  ProjectResponse,
} from "@/lib/types";
import {
  MatrixHeader,
  ProjectSelector,
  MatrixTable,
  MatrixEmptyState,
  MatrixStats,
} from "@/components/matrix";

export default function MatrixPage() {
  const { token } = useAuth();
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [rows, setRows] = useState<MatrixRowResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  // Load projects
  useEffect(() => {
    if (!token) return;
    apiFetch<ProjectListResponse>("/projects", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((data) => {
        setProjects(data.projects || []);
        if (data.projects?.length === 1)
          setSelectedProjectId(data.projects[0].id);
      })
      .catch(() => toast.error("Failed to load projects"));
  }, [token]);

  // Load matrix rows
  const fetchRows = useCallback(async () => {
    if (!token || !selectedProjectId) return;
    setLoading(true);
    try {
      const data = await apiFetch<MatrixListResponse>(
        `/projects/${selectedProjectId}/matrix`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setRows(data.items || []);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load matrix");
    } finally {
      setLoading(false);
    }
  }, [token, selectedProjectId]);

  useEffect(() => {
    fetchRows();
  }, [fetchRows]);

  // Generate matrix (async background job)
  async function handleGenerate() {
    if (!token || !selectedProjectId) return;
    setGenerating(true);
    try {
      const result = await apiFetch<{ job_id?: string; status?: string; total?: number; error?: string }>(
        `/projects/${selectedProjectId}/matrix:generate`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        },
      );

      if (result.job_id && result.status === "running") {
        toast.info(`Generating matrix for ${result.total} papers...`);
        await pollMatrixJob(result.job_id);
      }

      await fetchRows();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Generation failed",
      );
    } finally {
      setGenerating(false);
    }
  }

  async function pollMatrixJob(jobId: string) {
    const maxAttempts = 120; // 4 minutes max (20 papers × ~10s each)
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const job = await apiFetch<{ status: string; progress: number; total: number; result?: { created_count: number; skipped_count: number }; error_message?: string }>(
          `/papers/search/jobs/${jobId}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (job.status === "completed") {
          toast.success(`Generated ${job.result?.created_count ?? 0} rows (${job.result?.skipped_count ?? 0} skipped)`);
          return;
        }
        if (job.status === "failed") {
          toast.error(job.error_message || "Matrix generation failed");
          return;
        }
        if (job.progress > 0) {
          toast.info(`Processed ${job.progress}/${job.total} papers...`, { autoClose: 1000 });
        }
      } catch {
        // Ignore polling errors, keep trying
      }
    }
    toast.warning("Matrix generation is still running. Check back later.");
  }

  // Edit cell
  async function handleEdit(rowId: string, field: string, value: string) {
    if (!token) return;
    try {
      const updated = await apiFetch<MatrixRowResponse>(
        `/projects/${selectedProjectId}/matrix/${rowId}`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ [field]: value }),
        },
      );
      setRows((prev) =>
        prev.map((r) => (r.id === rowId ? { ...r, ...updated } : r)),
      );
      toast.success("Cell updated");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    }
  }

  // Delete row
  async function handleDelete(rowId: string) {
    if (!token || !confirm("Delete this matrix row?")) return;
    try {
      await apiFetch(`/projects/${selectedProjectId}/matrix/${rowId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      setRows((prev) => prev.filter((r) => r.id !== rowId));
      toast.success("Row deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
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
