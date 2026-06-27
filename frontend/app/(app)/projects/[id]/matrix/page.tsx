"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Eraser,
  ListChecks,
  Play,
  Spinner,
  Warning,
} from "@phosphor-icons/react";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useMatrixStore } from "@/lib/stores/matrix-store";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import {
  MatrixActionMenu,
  type MatrixActionItem,
} from "@/components/matrix/MatrixActionMenu";
import {
  MatrixHeader,
  MatrixTable,
  MatrixEmptyState,
  MatrixStats,
} from "@/components/matrix";

export default function ProjectMatrixPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = id ?? "";
  const token = useAuthStore((s) => s.token);

  const [jobProgress, setJobProgress] = useState<{
    processed: number;
    total: number;
    current: string;
  } | null>(null);

  const setSelectedProjectId = useMatrixStore((s) => s.setSelectedProjectId);
  const rows = useMatrixStore((s) => s.rows);
  const schema = useMatrixStore((s) => s.schema);
  const loading = useMatrixStore((s) => s.loading);
  const generating = useMatrixStore((s) => s.generating);
  const lowCount = useMatrixStore((s) => s.lowCount);
  const fetchRows = useMatrixStore((s) => s.fetchRows);
  const fetchSchema = useMatrixStore((s) => s.fetchSchema);
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

  useEffect(() => {
    if (!projectId) return;
    void fetchRows(projectId).catch(() =>
      toast.error("Failed to load matrix"),
    );
    void fetchSchema(projectId).catch(() => undefined);
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

  async function handleEdit(
    rowId: string,
    field: string,
    value: string | number | boolean | string[] | null,
  ) {
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

  async function handleExport(format: "md" | "csv") {
    if (!projectId || !token) return;
    try {
      const res = await fetch(
        `/api/projects/${projectId}/matrix:export.${format}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) {
        throw new Error(`Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `matrix.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Export failed",
      );
    }
  }

  const exportItems: MatrixActionItem[] = [
    {
      key: "md",
      label: "Download Markdown",
      description: "Human-readable .md keyed by the project schema",
      icon: <span className="font-mono text-[11px] font-bold text-charcoal">.md</span>,
      onClick: () => void handleExport("md"),
    },
    {
      key: "csv",
      label: "Download CSV",
      description: "One column per schema field, opens in Excel/Sheets",
      icon: <span className="font-mono text-[11px] font-bold text-charcoal">.csv</span>,
      onClick: () => void handleExport("csv"),
    },
  ];

  const cleanupItems: MatrixActionItem[] = [
    ...(lowCount > 0
      ? [
          {
            key: "remove-low",
            label: "Remove low-confidence rows",
            description: "Delete every row flagged 'low' (saved papers stay)",
            icon: <Warning size={14} weight="fill" />,
            destructive: true,
            badge: lowCount,
            disabled: removingLow || generating,
            onClick: handleRemoveLow,
          },
        ]
      : []),
    {
      key: "open-schema",
      label: "Edit extraction schema",
      description: "Add/remove custom fields, change column types",
      icon: <ListChecks size={14} />,
      onClick: () => router.push(`/projects/${projectId}/schema`),
    },
  ];

  return (
    <div>
      {/* ── Compact toolbar ──────────────────────────────────────────── */}
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h2
            className="font-display text-[20px] sm:text-[22px] font-bold leading-[1.1] text-ink"
            style={{ letterSpacing: "-0.4px" }}
          >
            Literature Matrix
          </h2>
          <p className="mt-0.5 font-ui text-[12px] text-charcoal">
            Compare methods, datasets, and findings across saved papers.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {rows.length > 0 && token && (
            <MatrixActionMenu
              label="Export"
              icon={<span className="font-mono text-[10px] font-bold">↓</span>}
              items={exportItems}
              testId="matrix-export-menu"
            />
          )}
          {rows.length > 0 && (
            <MatrixActionMenu
              label="Cleanup"
              icon={<Eraser size={12} weight="bold" />}
              items={cleanupItems}
              testId="matrix-cleanup-menu"
            />
          )}
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="focus-ring font-ui inline-flex h-[32px] items-center gap-1.5 rounded-full bg-primary px-3.5 text-[12px] font-semibold text-on-primary transition-all hover:bg-primary-deep active:scale-95 disabled:opacity-50"
          >
            {generating ? (
              <Spinner size={13} className="animate-spin" />
            ) : (
              <Play size={12} weight="fill" />
            )}
            {generating ? "Generating…" : "Generate"}
          </button>
        </div>
      </div>

      <MatrixHeader progress={jobProgress} generating={generating} />

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
          schema={schema}
          onEdit={handleEdit}
          onDelete={handleDelete}
        />
      )}

      <MatrixStats rows={rows} />
    </div>
  );
}
