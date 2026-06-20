"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Play, Spinner } from "@phosphor-icons/react";
import { useMatrixStore } from "@/lib/stores/matrix-store";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import {
  MatrixHeader,
  MatrixTable,
  MatrixEmptyState,
  MatrixStats,
} from "@/components/matrix";

export default function ProjectMatrixPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ?? "";

  const [jobProgress, setJobProgress] = useState<{
    processed: number;
    total: number;
    current: string;
  } | null>(null);

  const setSelectedProjectId = useMatrixStore((s) => s.setSelectedProjectId);
  const rows = useMatrixStore((s) => s.rows);
  const loading = useMatrixStore((s) => s.loading);
  const generating = useMatrixStore((s) => s.generating);
  const fetchRows = useMatrixStore((s) => s.fetchRows);
  const generate = useMatrixStore((s) => s.generate);
  const editRow = useMatrixStore((s) => s.editRow);
  const deleteRow = useMatrixStore((s) => s.deleteRow);

  useEffect(() => {
    if (projectId) setSelectedProjectId(projectId);
  }, [projectId, setSelectedProjectId]);

  const { poll: pollMatrixJob } = useJobPolling({
    onSuccess: (result) => {
      setJobProgress(null);
      return `Generated ${(result.created_count as number) ?? 0} rows (${(result.skipped_count as number) ?? 0} skipped)`;
    },
    onProgress: (progress, total, details) => {
      setJobProgress({
        processed: progress,
        total,
        current: details?.current ?? "",
      });
      return details?.current
        ? `Processed ${progress}/${total}: ${details.current}`
        : `Processed ${progress}/${total} papers...`;
    },
  });

  // Always re-fetch when the project id changes (handles direct URL navigation)
  useEffect(() => {
    if (!projectId) return;
    void fetchRows(projectId).catch(() =>
      toast.error("Failed to load matrix"),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function handleGenerate() {
    if (!projectId) return;
    try {
      await generate(projectId, async (jobId, total) => {
        setJobProgress({
          processed: 0,
          total: total ?? 0,
          current: "",
        });
        await pollMatrixJob(jobId);
        return null;
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setJobProgress(null);
    }
  }

  async function handleEdit(rowId: string, field: string, value: string) {
    if (!projectId) return;
    const updated = await editRow(projectId, rowId, field, value);
    if (updated) toast.success("Cell updated");
    else toast.error("Update failed");
  }

  async function handleDelete(rowId: string) {
    if (!projectId) return;
    if (!confirm("Delete this matrix row?")) return;
    const ok = await deleteRow(projectId, rowId);
    if (ok) toast.success("Row deleted");
    else toast.error("Delete failed");
  }

  return (
    <div>
      <div className="mb-4 sm:mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-[20px] sm:text-[22px] font-bold leading-[1.1] text-ink">
            Literature Matrix
          </h2>
          <p className="mt-1 font-ui text-[12px] text-charcoal">
            Compare methods, datasets, and findings across saved papers.
          </p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="focus-ring font-ui inline-flex h-[36px] sm:h-[40px] shrink-0 items-center gap-2 self-start rounded-full bg-primary px-4 sm:px-5 text-[12px] sm:text-[13px] font-semibold text-on-primary transition-all hover:bg-primary-deep active:scale-95 disabled:opacity-50"
        >
          {generating ? (
            <Spinner size={14} className="animate-spin" />
          ) : (
            <Play size={14} weight="fill" />
          )}
          {generating ? "Generating…" : "Generate Matrix"}
        </button>
      </div>

      <MatrixHeader
        progress={jobProgress}
        generating={generating}
      />

      {loading || rows.length === 0 ? (
        <MatrixEmptyState
          loading={loading}
          hasProject={true}
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
  );
}
