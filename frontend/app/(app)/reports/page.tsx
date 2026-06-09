"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type {
  ReportResponse,
  ReportListResponse,
  ReportDetailResponse,
  ProjectListResponse,
  ProjectResponse,
} from "@/lib/types";
import {
  PencilLine,
  CaretDown,
  CaretUp,
  Download,
  CheckCircle,
  XCircle,
  ArrowCounterClockwise,
  FileText,
} from "@phosphor-icons/react";
import { Dropdown } from "@/components/ui/Dropdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ReportsPage() {
  const { token } = useAuth();
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detailMap, setDetailMap] = useState<Record<string, ReportDetailResponse>>({});

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

  // Load reports
  const fetchReports = useCallback(async () => {
    if (!token || !selectedProjectId) return;
    setLoading(true);
    try {
      const data = await apiFetch<ReportListResponse>(
        `/projects/${selectedProjectId}/reports`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setReports(data.items || []);
    } catch {
      setReports([]);
    } finally {
      setLoading(false);
    }
  }, [token, selectedProjectId]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  // Generate report
  async function handleGenerate() {
    if (!token || !selectedProjectId) return;
    setGenerating(true);
    try {
      const result = await apiFetch<{ job_id?: string; status?: string }>(
        `/projects/${selectedProjectId}/reports`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ include_gap_section: true }),
        },
      );

      if (result.job_id && result.status === "running") {
        toast.info("Generating literature review...");
        await pollReportJob(result.job_id);
      }

      await fetchReports();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function pollReportJob(jobId: string) {
    const maxAttempts = 120; // 4 minutes max
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const job = await apiFetch<{
          status: string;
          progress: number;
          total: number;
          result?: { report_id?: string; validation_status?: string; total_citations?: number };
          error_message?: string;
        }>(`/papers/search/jobs/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (job.status === "completed") {
          const vs = job.result?.validation_status;
          const tc = job.result?.total_citations ?? 0;
          if (vs === "valid") {
            toast.success(`Report generated — ${tc} citations, all valid`);
          } else {
            toast.warning(`Report generated — ${tc} citations, some invalid`);
          }
          // Auto-expand the new report
          if (job.result?.report_id) {
            setExpandedId(job.result.report_id);
          }
          return;
        }
        if (job.status === "failed") {
          toast.error(job.error_message || "Report generation failed");
          return;
        }
      } catch {
        // Ignore polling errors, keep trying
      }
    }
    toast.warning("Report generation is still running. Check back later.");
  }

  // Load detail when expanding
  async function handleExpand(reportId: string) {
    if (expandedId === reportId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(reportId);

    if (detailMap[reportId]) return;

    if (!token || !selectedProjectId) return;
    try {
      const detail = await apiFetch<ReportDetailResponse>(
        `/projects/${selectedProjectId}/reports/${reportId}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setDetailMap((prev) => ({ ...prev, [reportId]: detail }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load report");
    }
  }

  // Export Markdown
  async function handleExport(reportId: string) {
    if (!token || !selectedProjectId) return;
    try {
      const result = await apiFetch<{ title: string; format: string; content: string }>(
        `/projects/${selectedProjectId}/reports/${reportId}/export`,
        { headers: { Authorization: `Bearer ${token}` } },
      );

      // Download as file
      const blob = new Blob([result.content], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${result.title.replace(/[^a-zA-Z0-9]/g, "_")}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Markdown exported");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    }
  }

  return (
    <div className="min-h-screen bg-canvas">
      <div className="mx-auto max-w-[1400px] px-6 py-8">
        <div className="flex flex-col gap-6">
          {/* Header */}
          <div className="flex items-end justify-between">
            <div>
              <h1
                className="font-display text-[32px] font-bold leading-[1.0] text-ink"
                style={{ letterSpacing: "-1px" }}
              >
                Literature Reviews
              </h1>
              <p className="mt-2 text-sm text-charcoal">
                Generate citation-safe literature review drafts from your
                matrix and research gaps.
              </p>
            </div>
          </div>

          {/* Project Selector */}
          <Dropdown
            options={projects.map((p) => ({
              value: p.id,
              label: p.title,
              description: `${p.paper_count} papers · ${p.status}`,
            }))}
            value={selectedProjectId}
            onChange={setSelectedProjectId}
            label="Project"
            placeholder="Select a project…"
          />

          {/* Generate Button */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleGenerate}
              disabled={!selectedProjectId || generating}
              className="focus-ring font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
            >
              {generating ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />
                  Generating…
                </>
              ) : (
                <>
                  <PencilLine size={16} />
                  Generate Review
                </>
              )}
            </button>
            {reports.length > 0 && (
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary/10 px-5 text-sm font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
              >
                <ArrowCounterClockwise size={16} />
                Regenerate
              </button>
            )}
          </div>

          {/* Report List */}
          {loading ? (
            <div className="space-y-4">
              {[1, 2].map((i) => (
                <div
                  key={i}
                  className="rounded-[10px] bg-surface-card p-5 animate-pulse"
                  style={{ border: "1px solid var(--hairline)" }}
                >
                  <div className="h-4 w-3/4 rounded bg-surface-bone" />
                  <div className="mt-2 h-3 w-1/2 rounded bg-surface-bone" />
                </div>
              ))}
            </div>
          ) : reports.length === 0 ? (
            <div
              className="flex flex-col items-center justify-center py-20 text-center rounded-[12px] bg-surface-card"
              style={{ border: "1px solid var(--hairline)" }}
            >
              <FileText size={40} className="text-stone mb-4" />
              <p className="font-ui text-base font-semibold text-ink">
                No reports yet
              </p>
              <p className="mt-2 text-sm text-charcoal max-w-md">
                Generate a literature matrix and research gaps first, then
                use this tool to create a citation-safe literature review.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {reports.map((report) => (
                <ReportCard
                  key={report.id}
                  report={report}
                  detail={detailMap[report.id]}
                  expanded={expandedId === report.id}
                  onToggle={() => handleExpand(report.id)}
                  onExport={() => handleExport(report.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Report Card ── */

function ReportCard({
  report,
  detail,
  expanded,
  onToggle,
  onExport,
}: {
  report: ReportResponse;
  detail?: ReportDetailResponse;
  expanded: boolean;
  onToggle: () => void;
  onExport: () => void;
}) {
  const audit = report.citation_audit;
  const isValid = report.validation_status === "valid";

  return (
    <div
      className="rounded-[10px] bg-surface-card transition-shadow hover:shadow-md"
      style={{ border: "1px solid var(--hairline)" }}
    >
      {/* Header */}
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") onToggle();
        }}
        className="flex w-full items-start gap-3 p-5 text-left cursor-pointer"
      >
        <div className="mt-0.5 shrink-0">
          <PencilLine size={20} className="text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-ui text-base font-semibold text-ink truncate">
              {report.title}
            </h3>
            <span
              className={`font-ui shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                isValid
                  ? "bg-green-50 text-green-700"
                  : "bg-red-50 text-red-700"
              }`}
            >
              {isValid ? (
                <CheckCircle size={12} />
              ) : (
                <XCircle size={12} />
              )}
              {isValid ? "Valid" : "Invalid"}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-3 font-ui text-[12px] text-ash">
            <span>{audit.total_citations} citations</span>
            <span>{audit.valid_citations} valid</span>
            {audit.invalid_citations > 0 && (
              <span className="text-red-600">
                {audit.invalid_citations} invalid
              </span>
            )}
            <span>{audit.uncited_saved_papers} uncited papers</span>
          </div>
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onExport();
            }}
            className="flex items-center gap-1.5 h-[32px] rounded-full bg-primary/10 px-3 font-ui text-[12px] font-semibold text-primary hover:bg-primary/20 transition-colors"
          >
            <Download size={14} />
            Export
          </button>
          {expanded ? (
            <CaretUp size={16} className="text-charcoal" />
          ) : (
            <CaretDown size={16} className="text-charcoal" />
          )}
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="px-5 pb-5 space-y-6 border-t border-[var(--hairline)] pt-4">
          {/* Citation Audit */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              label="Total Citations"
              value={audit.total_citations}
              color="text-ink"
            />
            <StatCard
              label="Valid"
              value={audit.valid_citations}
              color="text-green-700"
            />
            <StatCard
              label="Invalid"
              value={audit.invalid_citations}
              color={audit.invalid_citations > 0 ? "text-red-700" : "text-ash"}
            />
            <StatCard
              label="Uncited Papers"
              value={audit.uncited_saved_papers}
              color="text-ash"
            />
          </div>

          {/* References */}
          {detail && detail.references.length > 0 && (
            <div>
              <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-2">
                References ({detail.references.length})
              </p>
              <div className="space-y-2">
                {detail.references.map((ref) => (
                  <div
                    key={ref.project_paper_id}
                    className="rounded-[8px] bg-surface-bone px-4 py-3"
                  >
                    <p className="font-ui text-sm font-medium text-ink">
                      <span className="text-primary font-semibold">
                        {ref.citation_label}
                      </span>{" "}
                      {ref.title}
                    </p>
                    <p className="mt-0.5 text-[12px] text-charcoal">
                      {ref.authors.slice(0, 3).join(", ")}
                      {ref.authors.length > 3 && " et al."}
                      {ref.year && ` (${ref.year})`}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Markdown Preview */}
          {detail && (
            <div>
              <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-2">
                Preview
              </p>
              <div
                className="rounded-[10px] bg-surface-bone p-6 prose prose-sm max-w-none
                  prose-headings:font-display prose-headings:text-ink
                  prose-p:text-ink prose-p:leading-relaxed
                  prose-strong:text-ink
                  prose-li:text-ink
                  prose-a:text-primary prose-a:no-underline hover:prose-a:underline"
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {detail.content_markdown}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div
      className="rounded-[8px] bg-surface-bone px-4 py-3 text-center"
    >
      <p className={`font-display text-[24px] font-bold ${color}`}>{value}</p>
      <p className="font-ui text-[11px] text-ash mt-0.5">{label}</p>
    </div>
  );
}
