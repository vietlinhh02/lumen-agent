"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Play, Spinner, Trash, Warning } from "@phosphor-icons/react";
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
  const lowCount = useMatrixStore((s) => s.lowCount);
  const fetchRows = useMatrixStore((s) => s.fetchRows);
  const generate = useMatrixStore((s) => s.generate);
  const editRow = useMatrixStore((s) => s.editRow);
  const deleteRow = useMatrixStore((s) => s.deleteRow);
  const bulkDeleteLow = useMatrixStore((s) => s.bulkDeleteLow);

  const [removingLow, setRemovingLow] = useState(false);

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

  async function handleRemoveLow() {
    if (!projectId) return;
    if (lowCount === 0) {
      toast.info("No low-confidence rows to remove");
      return;
    }
    const ok = confirm(
      `Remove all ${lowCount} low-confidence matrix row${lowCount === 1 ? "" : "s"}?\n\n` +
        "The underlying saved papers will stay in your project — only the matrix rows are deleted. " +
        "You can re-generate the matrix afterwards to fill them back in.",
    );
    if (!ok) return;
    setRemovingLow(true);
    try {
      const deleted = await bulkDeleteLow(projectId);
      if (deleted > 0) {
        toast.success(`Removed ${deleted} low-confidence row${deleted === 1 ? "" : "s"}`);
      } else {
        toast.info("Nothing to remove");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Remove failed");
    } finally {
      setRemovingLow(false);
    }
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
        <div className="flex shrink-0 items-center gap-2 self-start">
          {lowCount > 0 && (
            <button
              onClick={handleRemoveLow}
              disabled={removingLow || generating}
              title="Delete every row flagged 'low' confidence. The saved papers stay — only the matrix rows are removed."
              className="focus-ring font-ui inline-flex h-[36px] sm:h-[40px] items-center gap-1.5 rounded-full bg-red-50 px-4 text-[12px] sm:text-[13px] font-semibold text-red-700 transition-all hover:bg-red-100 active:scale-95 disabled:opacity-50"
            >
              {removingLow ? (
                <Spinner size={13} className="animate-spin" />
              ) : (
                <Warning size={13} weight="fill" />
              )}
              Remove {lowCount} low
            </button>
          )}
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="focus-ring font-ui inline-flex h-[36px] sm:h-[40px] items-center gap-2 rounded-full bg-primary px-4 sm:px-5 text-[12px] sm:text-[13px] font-semibold text-on-primary transition-all hover:bg-primary-deep active:scale-95 disabled:opacity-50"
          >
            {generating ? (
              <Spinner size={14} className="animate-spin" />
            ) : (
              <Play size={14} weight="fill" />
            )}
            {generating ? "Generating…" : "Generate Matrix"}
          </button>
        </div>
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
