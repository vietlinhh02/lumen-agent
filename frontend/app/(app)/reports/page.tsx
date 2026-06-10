"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { PencilLine } from "@phosphor-icons/react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { useProjects } from "@/lib/hooks/useProjects";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { parseSections, buildToc } from "@/lib/markdown";
import { ProjectSelector } from "@/components/ProjectSelector";
import { ReportList, ReportToolbar, ReportContent } from "@/components/reports";
import type { ReportResponse, ReportListResponse, ReportDetailResponse } from "@/lib/types";

export default function ReportsPage() {
  const { token } = useAuth();
  const { projects } = useProjects();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReportDetailResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSection, setActiveSection] = useState<string | null>(null);

  const { poll } = useJobPolling({
    onSuccess: (result) => {
      const vs = result.validation_status as string;
      const tc = (result.total_citations as number) ?? 0;
      if (vs === "valid") setSelectedId(result.report_id as string);
      return vs === "valid" ? `${tc} citations, all valid` : `${tc} citations, some invalid`;
    },
  });

  useEffect(() => {
    if (projects.length === 1) setSelectedProjectId(projects[0].id);
  }, [projects]);

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
        toast.error(err instanceof Error ? err.message : "Failed to load report");
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

  async function handleGenerate() {
    if (!token || !selectedProjectId) return;
    setGenerating(true);
    try {
      const result = await apiFetch<{ job_id?: string; status?: string }>(
        `/projects/${selectedProjectId}/reports`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ include_gap_section: true }),
        },
      );
      if (result.job_id && result.status === "running") {
        toast.info("Generating literature review...");
        await poll(result.job_id);
      }
      await fetchReports();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

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

  const parsedSections = useMemo(
    () => (detail ? parseSections(detail.content_markdown) : []),
    [detail],
  );
  const toc = useMemo(() => buildToc(parsedSections), [parsedSections]);
  const filteredSections = useMemo(
    () =>
      parsedSections.filter(
        (s) =>
          !searchQuery.trim() ||
          s.heading.toLowerCase().includes(searchQuery.toLowerCase()) ||
          s.content.toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [parsedSections, searchQuery],
  );

  return (
    <div className="fixed inset-0 top-[60px] bg-canvas flex flex-col overflow-hidden z-10 ml-0 xl:ml-[56px]">
      <div
        className="shrink-0 px-4 sm:px-6 pt-3 pb-2.5 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4"
        style={{ borderBottom: "1px solid var(--hairline)" }}
      >
        <div className="flex items-center gap-3 sm:gap-4 min-w-0">
          <h1
            className="font-display text-[18px] sm:text-[20px] font-bold leading-none text-ink shrink-0"
            style={{ letterSpacing: "-0.5px" }}
          >
            Literature Reviews
          </h1>
          <div className="h-5 w-px bg-[var(--hairline)] shrink-0 hidden sm:block" />
        </div>
        <div className="flex-1 min-w-0 max-w-xs">
          <ProjectSelector
            projects={projects}
            selectedId={selectedProjectId}
            onChange={setSelectedProjectId}
            showStatus={false}
          />
        </div>
      </div>

      <div className="flex-1 flex min-h-0">
        <ReportList
          reports={reports}
          selectedId={selectedId}
          loading={loading}
          generating={generating}
          onSelect={setSelectedId}
          onGenerate={handleGenerate}
        />

        <div className={`flex-1 bg-canvas flex flex-col min-w-0 transition-all duration-200 ease-out ${selectedId ? "flex" : "hidden md:flex"}`}>
          {!selectedId ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <PencilLine size={40} className="text-stone/40 mb-3" />
              <p className="font-ui text-sm font-semibold text-charcoal">Select a report</p>
            </div>
          ) : loadingDetail ? (
            <div className="flex-1 p-8 space-y-4">
              <div className="h-8 w-2/3 rounded bg-surface-bone animate-pulse" />
              <div className="h-64 rounded bg-surface-bone animate-pulse" />
            </div>
          ) : detail ? (
            <>
              <ReportToolbar
                validationStatus={detail.validation_status}
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                toc={toc}
                activeSection={activeSection}
                onScrollToSection={(id) => setActiveSection(id)}
                onBack={() => {
                  setSelectedId(null);
                  setDetail(null);
                }}
                onExport={handleExport}
              />
              <ReportContent
                detail={detail}
                filteredSections={filteredSections}
                parsedSections={parsedSections}
                toc={toc}
                searchQuery={searchQuery}
                activeSection={activeSection}
                onSetActiveSection={setActiveSection}
              />
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
