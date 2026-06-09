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
  Download,
  CheckCircle,
  XCircle,
  ArrowCounterClockwise,
  FileText,
  ArrowLeft,
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

  // Selected report detail
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReportDetailResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

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
    setSelectedId(null);
    setDetail(null);
  }, [fetchReports]);

  // Load detail when selecting a report
  const fetchDetail = useCallback(async (reportId: string) => {
    if (!token || !selectedProjectId) return;
    setLoadingDetail(true);
    try {
      const d = await apiFetch<ReportDetailResponse>(
        `/projects/${selectedProjectId}/reports/${reportId}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setDetail(d);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setLoadingDetail(false);
    }
  }, [token, selectedProjectId]);

  useEffect(() => {
    if (selectedId) fetchDetail(selectedId);
    else setDetail(null);
  }, [selectedId, fetchDetail]);

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
    const maxAttempts = 120;
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const job = await apiFetch<{
          status: string;
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
          if (job.result?.report_id) {
            setSelectedId(job.result.report_id);
          }
          return;
        }
        if (job.status === "failed") {
          toast.error(job.error_message || "Report generation failed");
          return;
        }
      } catch {
        // Ignore polling errors
      }
    }
    toast.warning("Report is still generating. Check back later.");
  }

  // Export
  async function handleExport() {
    if (!token || !selectedProjectId || !selectedId) return;
    try {
      const result = await apiFetch<{ title: string; content: string }>(
        `/projects/${selectedProjectId}/reports/${selectedId}/export`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
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
      <div className="mx-auto max-w-[1500px] px-6 py-8">
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

          {/* Split View */}
          <div className="flex gap-0 rounded-[12px] overflow-hidden" style={{ border: "1px solid var(--hairline)", height: "calc(100vh - 280px)", minHeight: "500px" }}>
            {/* Left Panel — Report List */}
            <div className="w-[320px] shrink-0 bg-surface-card flex flex-col" style={{ borderRight: "1px solid var(--hairline)" }}>
              {/* List Header */}
              <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: "1px solid var(--hairline)" }}>
                <span className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide">
                  Reports ({reports.length})
                </span>
                <button
                  onClick={handleGenerate}
                  disabled={!selectedProjectId || generating}
                  className="focus-ring font-ui inline-flex items-center gap-1.5 h-[32px] rounded-full bg-primary px-3 text-[12px] font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
                >
                  {generating ? (
                    <>
                      <span className="h-3 w-3 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />
                      …
                    </>
                  ) : (
                    <>
                      <PencilLine size={12} />
                      New
                    </>
                  )}
                </button>
              </div>

              {/* List Items */}
              <div className="flex-1 overflow-y-auto">
                {loading ? (
                  <div className="p-4 space-y-3">
                    {[1, 2].map((i) => (
                      <div key={i} className="h-16 rounded-[8px] bg-surface-bone animate-pulse" />
                    ))}
                  </div>
                ) : reports.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full p-6 text-center">
                    <FileText size={32} className="text-stone mb-3" />
                    <p className="font-ui text-sm font-medium text-ink">No reports</p>
                    <p className="font-ui text-[12px] text-charcoal mt-1">
                      Generate a review to get started
                    </p>
                  </div>
                ) : (
                  <div className="p-2 space-y-1">
                    {reports.map((r) => (
                      <button
                        key={r.id}
                        onClick={() => setSelectedId(r.id)}
                        className={`w-full text-left rounded-[8px] px-3 py-3 transition-colors ${
                          selectedId === r.id
                            ? "bg-primary/10"
                            : "hover:bg-surface-bone"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className={`shrink-0 inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                              r.validation_status === "valid"
                                ? "bg-green-50 text-green-700"
                                : "bg-red-50 text-red-700"
                            }`}
                          >
                            {r.validation_status === "valid" ? (
                              <CheckCircle size={10} />
                            ) : (
                              <XCircle size={10} />
                            )}
                            {r.validation_status === "valid" ? "Valid" : "Invalid"}
                          </span>
                        </div>
                        <p className="font-ui text-[13px] font-medium text-ink mt-1 line-clamp-2">
                          {r.title}
                        </p>
                        <p className="font-ui text-[11px] text-ash mt-1">
                          {r.citation_audit.total_citations} citations
                        </p>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Regenerate button at bottom */}
              {reports.length > 0 && (
                <div className="px-4 py-3" style={{ borderTop: "1px solid var(--hairline)" }}>
                  <button
                    onClick={handleGenerate}
                    disabled={generating}
                    className="font-ui w-full inline-flex items-center justify-center gap-2 h-[36px] rounded-full bg-primary/10 text-[12px] font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
                  >
                    <ArrowCounterClockwise size={14} />
                    Regenerate
                  </button>
                </div>
              )}
            </div>

            {/* Right Panel — Preview */}
            <div className="flex-1 bg-canvas flex flex-col min-w-0">
              {!selectedId ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-8">
                  <PencilLine size={48} className="text-stone/40 mb-4" />
                  <p className="font-ui text-base font-semibold text-charcoal">
                    Select a report
                  </p>
                  <p className="font-ui text-sm text-ash mt-1 max-w-sm">
                    Choose a report from the list to preview its content,
                    references, and citation audit.
                  </p>
                </div>
              ) : loadingDetail ? (
                <div className="flex-1 p-8 space-y-4">
                  <div className="h-8 w-2/3 rounded bg-surface-bone animate-pulse" />
                  <div className="h-4 w-1/2 rounded bg-surface-bone animate-pulse" />
                  <div className="h-64 rounded bg-surface-bone animate-pulse" />
                </div>
              ) : detail ? (
                <>
                  {/* Preview Toolbar */}
                  <div
                    className="flex items-center justify-between px-6 py-3 bg-surface-card shrink-0"
                    style={{ borderBottom: "1px solid var(--hairline)" }}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <button
                        onClick={() => { setSelectedId(null); setDetail(null); }}
                        className="flex items-center gap-1 font-ui text-[12px] text-charcoal hover:text-ink transition-colors"
                      >
                        <ArrowLeft size={14} />
                        Back
                      </button>
                      <div className="h-4 w-px bg-[var(--hairline)]" />
                      <h2 className="font-ui text-sm font-semibold text-ink truncate">
                        {detail.title}
                      </h2>
                      <span
                        className={`shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                          detail.validation_status === "valid"
                            ? "bg-green-50 text-green-700"
                            : "bg-red-50 text-red-700"
                        }`}
                      >
                        {detail.validation_status === "valid" ? (
                          <CheckCircle size={12} />
                        ) : (
                          <XCircle size={12} />
                        )}
                        {detail.validation_status === "valid" ? "All citations valid" : "Invalid citations"}
                      </span>
                    </div>
                    <button
                      onClick={handleExport}
                      className="flex items-center gap-1.5 h-[32px] rounded-full bg-primary px-3 font-ui text-[12px] font-semibold text-on-primary hover:bg-primary-deep transition-colors"
                    >
                      <Download size={14} />
                      Export .md
                    </button>
                  </div>

                  {/* Scrollable Content */}
                  <div className="flex-1 overflow-y-auto">
                    <div className="max-w-[900px] mx-auto px-8 py-6 space-y-8">
                      {/* Citation Audit Bar */}
                      <div className="flex items-center gap-4 flex-wrap">
                        <AuditPill label="Citations" value={detail.citation_audit.total_citations} />
                        <AuditPill label="Valid" value={detail.citation_audit.valid_citations} color="text-green-700" />
                        {detail.citation_audit.invalid_citations > 0 && (
                          <AuditPill label="Invalid" value={detail.citation_audit.invalid_citations} color="text-red-700" />
                        )}
                        <AuditPill label="Uncited" value={detail.citation_audit.uncited_saved_papers} color="text-ash" />
                      </div>

                      {/* References */}
                      {detail.references.length > 0 && (
                        <div>
                          <h3 className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-3">
                            References ({detail.references.length})
                          </h3>
                          <div className="grid gap-2">
                            {detail.references.map((ref) => (
                              <div
                                key={ref.project_paper_id}
                                className="rounded-[8px] bg-surface-card px-4 py-3"
                                style={{ border: "1px solid var(--hairline)" }}
                              >
                                <p className="font-ui text-sm text-ink">
                                  <span className="font-semibold text-primary">
                                    {ref.citation_label}
                                  </span>{" "}
                                  {ref.title}
                                </p>
                                <p className="font-ui text-[12px] text-charcoal mt-0.5">
                                  {ref.authors.slice(0, 3).join(", ")}
                                  {ref.authors.length > 3 && " et al."}
                                  {ref.year && ` (${ref.year})`}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Markdown Content */}
                      <div>
                        <h3 className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-3">
                          Literature Review
                        </h3>
                        <div
                          className="rounded-[12px] bg-surface-card p-8 prose prose-sm max-w-none
                            prose-headings:font-display prose-headings:text-ink prose-headings:tracking-tight
                            prose-h2:text-[20px] prose-h2:mt-8 prose-h2:mb-3
                            prose-p:text-ink prose-p:leading-[1.7] prose-p:text-[14px]
                            prose-strong:text-ink prose-strong:font-semibold
                            prose-li:text-ink prose-li:text-[14px]
                            prose-a:text-primary prose-a:no-underline hover:prose-a:underline
                            prose-blockquote:border-l-primary prose-blockquote:text-charcoal"
                          style={{ border: "1px solid var(--hairline)" }}
                        >
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {detail.content_markdown}
                          </ReactMarkdown>
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AuditPill({ label, value, color = "text-ink" }: { label: string; value: number; color?: string }) {
  return (
    <span className="font-ui inline-flex items-center gap-1.5 text-[12px] text-charcoal">
      <span className={`font-display text-[16px] font-bold ${color}`}>{value}</span>
      {label}
    </span>
  );
}
