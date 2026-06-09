"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  MagnifyingGlass,
  List,
} from "@phosphor-icons/react";
import { Dropdown } from "@/components/ui/Dropdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/* ── Types ── */

interface TocEntry {
  id: string;
  text: string;
  level: number;
}

interface ParsedSection {
  id: string;
  heading: string;
  level: number;
  content: string;
}

/* ── Helpers ── */

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function parseSections(markdown: string): ParsedSection[] {
  const lines = markdown.split("\n");
  const sections: ParsedSection[] = [];
  let current: ParsedSection | null = null;

  for (const line of lines) {
    const match = line.match(/^(#{1,3})\s+(.+)$/);
    if (match) {
      if (current) sections.push(current);
      const heading = match[2].replace(/\*+/g, "").trim();
      current = {
        id: slugify(heading),
        heading,
        level: match[1].length,
        content: "",
      };
    } else if (current) {
      current.content += line + "\n";
    } else {
      // Content before first heading — create implicit section
      current = {
        id: "_intro",
        heading: "",
        level: 1,
        content: line + "\n",
      };
    }
  }
  if (current) sections.push(current);
  return sections;
}

function buildToc(sections: ParsedSection[]): TocEntry[] {
  return sections
    .filter((s) => s.heading)
    .map((s) => ({ id: s.id, text: s.heading, level: s.level }));
}

/* ── Main Page ── */

export default function ReportsPage() {
  const { token } = useAuth();
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReportDetailResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Search within review
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sectionRefs = useRef<Record<string, HTMLElement>>({});

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

  // Load detail
  const fetchDetail = useCallback(
    async (reportId: string) => {
      if (!token || !selectedProjectId) return;
      setLoadingDetail(true);
      try {
        const d = await apiFetch<ReportDetailResponse>(
          `/projects/${selectedProjectId}/reports/${reportId}`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        setDetail(d);
        setActiveSection(null);
        setSearchQuery("");
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Failed to load report",
        );
      } finally {
        setLoadingDetail(false);
      }
    },
    [token, selectedProjectId],
  );

  useEffect(() => {
    if (selectedId) fetchDetail(selectedId);
    else setDetail(null);
  }, [selectedId, fetchDetail]);

  // Track active section on scroll
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
          }
        }
      },
      { root: container, rootMargin: "-80px 0px -60% 0px", threshold: 0 },
    );

    const sections = container.querySelectorAll("[data-section]");
    sections.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, [detail]);

  // Generate
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
    const max = 120;
    for (let i = 0; i < max; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const job = await apiFetch<{
          status: string;
          result?: {
            report_id?: string;
            validation_status?: string;
            total_citations?: number;
          };
          error_message?: string;
        }>(`/papers/search/jobs/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (job.status === "completed") {
          const vs = job.result?.validation_status;
          const tc = job.result?.total_citations ?? 0;
          vs === "valid"
            ? toast.success(`${tc} citations, all valid`)
            : toast.warning(`${tc} citations, some invalid`);
          if (job.result?.report_id) setSelectedId(job.result.report_id);
          return;
        }
        if (job.status === "failed") {
          toast.error(job.error_message || "Failed");
          return;
        }
      } catch {
        /* ignore */
      }
    }
  }

  // Export
  async function handleExport() {
    if (!token || !selectedProjectId || !selectedId) return;
    try {
      const r = await apiFetch<{ title: string; content: string }>(
        `/projects/${selectedProjectId}/reports/${selectedId}/export`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      const blob = new Blob([r.content], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${r.title.replace(/[^a-zA-Z0-9]/g, "_")}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Exported");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    }
  }

  // Scroll to section
  function scrollToSection(id: string) {
    const el = sectionRefs.current[id];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      setActiveSection(id);
    }
  }

  // Filter sections by search
  function matchesSearch(section: ParsedSection): boolean {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      section.heading.toLowerCase().includes(q) ||
      section.content.toLowerCase().includes(q)
    );
  }

  const parsedSections = detail ? parseSections(detail.content_markdown) : [];
  const toc = detail ? buildToc(parsedSections) : [];
  const filteredSections = parsedSections.filter(matchesSearch);

  return (
    <div className="h-screen bg-canvas flex flex-col overflow-hidden">
      {/* Compact Header — fixed */}
      <div className="shrink-0 px-4 sm:px-6 pt-4 pb-3 flex items-center gap-4" style={{ borderBottom: "1px solid var(--hairline)" }}>
        <h1
          className="font-display text-[20px] font-bold leading-none text-ink shrink-0"
          style={{ letterSpacing: "-0.5px" }}
        >
          Literature Reviews
        </h1>
        <div className="h-5 w-px bg-[var(--hairline)] shrink-0" />
        <div className="flex-1 min-w-0 max-w-xs">
          <Dropdown
            options={projects.map((p) => ({
              value: p.id,
              label: p.title,
              description: `${p.paper_count} papers`,
            }))}
            value={selectedProjectId}
            onChange={setSelectedProjectId}
            placeholder="Select project…"
          />
        </div>
      </div>

      {/* Split View — fills remaining height */}
      <div
        className="flex-1 flex min-h-0"
      >
            {/* ── Left Panel: Report List ── */}
            <div
              className="w-[240px] shrink-0 bg-surface-card flex flex-col"
              style={{ borderRight: "1px solid var(--hairline)" }}
            >
              <div
                className="px-4 py-3 flex items-center justify-between"
                style={{ borderBottom: "1px solid var(--hairline)" }}
              >
                <span className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide">
                  Reports ({reports.length})
                </span>
                <button
                  onClick={handleGenerate}
                  disabled={!selectedProjectId || generating}
                  className="focus-ring font-ui inline-flex items-center gap-1.5 h-[28px] rounded-full bg-primary px-2.5 text-[11px] font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
                >
                  {generating ? (
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />
                  ) : (
                    <PencilLine size={11} />
                  )}
                  New
                </button>
              </div>

              <div className="flex-1 overflow-y-auto scrollbar-hide">
                {loading ? (
                  <div className="p-3 space-y-2">
                    {[1, 2].map((i) => (
                      <div
                        key={i}
                        className="h-14 rounded bg-surface-bone animate-pulse"
                      />
                    ))}
                  </div>
                ) : reports.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full p-4 text-center">
                    <FileText size={28} className="text-stone mb-2" />
                    <p className="font-ui text-[13px] font-medium text-ink">
                      No reports
                    </p>
                  </div>
                ) : (
                  <div className="p-1.5 space-y-0.5">
                    {reports.map((r) => (
                      <button
                        key={r.id}
                        onClick={() => setSelectedId(r.id)}
                        className={`w-full text-left rounded-[8px] px-3 py-2.5 transition-colors ${
                          selectedId === r.id
                            ? "bg-primary/10"
                            : "hover:bg-surface-bone"
                        }`}
                      >
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                            r.validation_status === "valid"
                              ? "bg-green-50 text-green-700"
                              : "bg-red-50 text-red-700"
                          }`}
                        >
                          {r.validation_status === "valid" ? (
                            <CheckCircle size={9} />
                          ) : (
                            <XCircle size={9} />
                          )}
                          {r.validation_status === "valid" ? "Valid" : "Bad"}
                        </span>
                        <p className="font-ui text-[12px] font-medium text-ink mt-1 line-clamp-2">
                          {r.title}
                        </p>
                        <p className="font-ui text-[10px] text-ash mt-0.5">
                          {r.citation_audit.total_citations} citations
                        </p>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {reports.length > 0 && (
                <div
                  className="px-3 py-2.5"
                  style={{ borderTop: "1px solid var(--hairline)" }}
                >
                  <button
                    onClick={handleGenerate}
                    disabled={generating}
                    className="font-ui w-full inline-flex items-center justify-center gap-1.5 h-[32px] rounded-full bg-primary/10 text-[11px] font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
                  >
                    <ArrowCounterClockwise size={12} />
                    Regenerate
                  </button>
                </div>
              )}
            </div>

            {/* ── Right Panel: Preview ── */}
            <div className="flex-1 bg-canvas flex flex-col min-w-0">
              {!selectedId ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-8">
                  <PencilLine size={40} className="text-stone/40 mb-3" />
                  <p className="font-ui text-sm font-semibold text-charcoal">
                    Select a report
                  </p>
                </div>
              ) : loadingDetail ? (
                <div className="flex-1 p-8 space-y-4">
                  <div className="h-8 w-2/3 rounded bg-surface-bone animate-pulse" />
                  <div className="h-64 rounded bg-surface-bone animate-pulse" />
                </div>
              ) : detail ? (
                <>
                  {/* ── Toolbar ── */}
                  <div
                    className="flex items-center gap-3 px-4 py-2.5 bg-surface-card shrink-0"
                    style={{
                      borderBottom: "1px solid var(--hairline)",
                    }}
                  >
                    <button
                      onClick={() => {
                        setSelectedId(null);
                        setDetail(null);
                      }}
                      className="flex items-center gap-1 font-ui text-[12px] text-charcoal hover:text-ink transition-colors shrink-0"
                    >
                      <ArrowLeft size={14} />
                    </button>
                    <div className="h-4 w-px bg-[var(--hairline)] shrink-0" />
                    <span
                      className={`shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        detail.validation_status === "valid"
                          ? "bg-green-50 text-green-700"
                          : "bg-red-50 text-red-700"
                      }`}
                    >
                      {detail.validation_status === "valid" ? (
                        <CheckCircle size={10} />
                      ) : (
                        <XCircle size={10} />
                      )}
                      {detail.validation_status === "valid" ? "Valid" : "Invalid"}
                    </span>

                    {/* Search */}
                    <div className="flex-1 max-w-xs relative">
                      <MagnifyingGlass
                        size={14}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-ash"
                      />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search in review…"
                        className="focus-ring h-[30px] w-full rounded-full bg-surface-bone pl-8 pr-3 font-ui text-[12px] text-ink outline-none"
                        style={{ border: "1px solid var(--hairline)" }}
                      />
                    </div>

                    {/* TOC dropdown */}
                    {toc.length > 0 && (
                      <TocDropdown
                        toc={toc}
                        activeId={activeSection}
                        onSelect={scrollToSection}
                      />
                    )}

                    <div className="flex-1" />

                    <button
                      onClick={handleExport}
                      className="flex items-center gap-1.5 h-[28px] rounded-full bg-primary px-3 font-ui text-[11px] font-semibold text-on-primary hover:bg-primary-deep transition-colors shrink-0"
                    >
                      <Download size={12} />
                      Export
                    </button>
                  </div>

                  {/* ── Content with TOC sidebar ── */}
                  <div className="flex-1 overflow-hidden flex">
                    {/* Main scroll area */}
                    <div
                      ref={scrollRef}
                      className="flex-1 overflow-y-auto scrollbar-hide"
                    >
                      <div className="max-w-[900px] mx-auto px-10 py-8 space-y-6">
                        {/* Citation Audit */}
                        <div className="flex items-center gap-5 flex-wrap">
                          <AuditPill
                            label="Citations"
                            value={detail.citation_audit.total_citations}
                          />
                          <AuditPill
                            label="Valid"
                            value={detail.citation_audit.valid_citations}
                            color="text-green-700"
                          />
                          {detail.citation_audit.invalid_citations > 0 && (
                            <AuditPill
                              label="Invalid"
                              value={detail.citation_audit.invalid_citations}
                              color="text-red-700"
                            />
                          )}
                        </div>

                        {/* References */}
                        {detail.references.length > 0 && (
                          <details className="group">
                            <summary className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide cursor-pointer hover:text-ink transition-colors list-none flex items-center gap-2">
                              <List size={14} />
                              References ({detail.references.length})
                              <span className="text-[10px] text-ash group-open:rotate-90 transition-transform">
                                ▸
                              </span>
                            </summary>
                            <div className="mt-3 grid gap-1.5">
                              {detail.references.map((ref) => (
                                <div
                                  key={ref.project_paper_id}
                                  className="rounded-[6px] bg-surface-card px-3 py-2"
                                  style={{
                                    border: "1px solid var(--hairline)",
                                  }}
                                >
                                  <p className="font-ui text-[13px] text-ink">
                                    <span className="font-semibold text-primary mr-1">
                                      {ref.citation_label}
                                    </span>
                                    {ref.title}
                                  </p>
                                  <p className="font-ui text-[11px] text-charcoal mt-0.5">
                                    {ref.authors.slice(0, 3).join(", ")}
                                    {ref.authors.length > 3 && " et al."}
                                    {ref.year && ` (${ref.year})`}
                                  </p>
                                </div>
                              ))}
                            </div>
                          </details>
                        )}

                        {/* Section Cards */}
                        {searchQuery.trim() && (
                          <p className="font-ui text-[12px] text-ash">
                            {filteredSections.length} of{" "}
                            {parsedSections.length} sections match &quot;
                            {searchQuery}&quot;
                          </p>
                        )}

                        {filteredSections.map((section) => (
                          <div
                            key={section.id}
                            id={section.id}
                            data-section
                            ref={(el) => {
                              if (el) sectionRefs.current[section.id] = el;
                            }}
                            className={`rounded-[12px] bg-surface-card transition-all ${
                              activeSection === section.id
                                ? "ring-2 ring-primary/20 shadow-sm"
                                : "hover:shadow-sm"
                            }`}
                            style={{
                              border: "1px solid var(--hairline)",
                              scrollMarginTop: "80px",
                            }}
                          >
                            {section.heading && (
                              <div
                                className="px-8 pt-6 pb-3"
                                style={{
                                  borderBottom: "1px solid var(--hairline)",
                                }}
                              >
                                <h2 className="font-display text-[20px] font-bold text-ink tracking-tight">
                                  {section.heading}
                                </h2>
                              </div>
                            )}
                            <div
                              className={`prose max-w-none px-8 ${section.heading ? "py-5" : "py-6"}
                                prose-p:text-ink prose-p:leading-[1.85] prose-p:text-[15px] prose-p:mb-4
                                prose-strong:text-ink prose-strong:font-semibold
                                prose-em:text-charcoal
                                prose-li:text-ink prose-li:text-[15px] prose-li:leading-[1.8] prose-li:mb-1
                                prose-ol:my-4 prose-ul:my-4
                                prose-a:text-primary prose-a:no-underline hover:prose-a:underline prose-a:font-medium
                                prose-blockquote:border-l-[3px] prose-blockquote:border-l-primary prose-blockquote:text-charcoal prose-blockquote:italic prose-blockquote:pl-5 prose-blockquote:my-4
                                prose-hr:my-6 prose-hr:border-[var(--hairline)]
                                prose-table:text-[14px] prose-table:my-4
                                prose-th:text-left prose-th:font-semibold prose-th:text-ink prose-th:pb-2 prose-th:border-b prose-th:border-[var(--hairline)]
                                prose-td:py-2 prose-td:border-b prose-td:border-[var(--hairline)]`}
                            >
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {section.content}
                              </ReactMarkdown>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* ── TOC Sidebar (right rail) ── */}
                    {toc.length > 2 && (
                      <div
                        className="hidden lg:block w-[220px] shrink-0 bg-surface-card/50 overflow-y-auto scrollbar-hide"
                        style={{
                          borderLeft: "1px solid var(--hairline)",
                        }}
                      >
                        <div className="px-3 py-4 sticky top-0">
                          <p className="font-ui text-[10px] font-semibold text-ash uppercase tracking-wide mb-2 px-1">
                            Contents
                          </p>
                          <nav className="space-y-0.5">
                            {toc.map((entry) => (
                              <button
                                key={entry.id}
                                onClick={() => scrollToSection(entry.id)}
                                className={`block w-full text-left font-ui text-[12px] px-2 py-1 rounded transition-colors ${
                                  entry.level === 3 ? "pl-5" : ""
                                } ${
                                  activeSection === entry.id
                                    ? "text-primary font-semibold bg-primary/5"
                                    : "text-charcoal hover:text-ink hover:bg-surface-bone"
                                }`}
                              >
                                {entry.text}
                              </button>
                            ))}
                          </nav>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              ) : null}
            </div>
          </div>
    </div>
  );
}

/* ── Components ── */

function TocDropdown({
  toc,
  activeId,
  onSelect,
}: {
  toc: TocEntry[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 h-[30px] rounded-full bg-surface-bone px-3 font-ui text-[11px] text-charcoal hover:text-ink transition-colors"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <List size={12} />
        Sections
      </button>
      {open && (
        <div
          className="absolute left-0 top-[36px] z-50 w-[220px] rounded-[10px] bg-surface-card p-1 shadow-lg max-h-[300px] overflow-y-auto scrollbar-hide"
          style={{ border: "1px solid var(--hairline)" }}
        >
          {toc.map((entry) => (
            <button
              key={entry.id}
              onClick={() => {
                onSelect(entry.id);
                setOpen(false);
              }}
              className={`block w-full text-left font-ui text-[12px] px-3 py-2 rounded-[6px] transition-colors ${
                entry.level === 3 ? "pl-6" : ""
              } ${
                activeId === entry.id
                  ? "bg-primary/10 text-primary font-semibold"
                  : "text-ink hover:bg-surface-bone"
              }`}
            >
              {entry.text}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function AuditPill({
  label,
  value,
  color = "text-ink",
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <span className="font-ui inline-flex items-center gap-1.5 text-[11px] text-charcoal">
      <span className={`font-display text-[15px] font-bold ${color}`}>
        {value}
      </span>
      {label}
    </span>
  );
}
