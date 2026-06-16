"use client";

import { useEffect, useMemo } from "react";
import { toast } from "sonner";
import { PencilLine } from "@phosphor-icons/react";
import { useProjects } from "@/lib/hooks/useProjects";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { useReportsStore } from "@/lib/stores/reports-store";
import { parseSections, buildToc } from "@/lib/markdown";
import { ProjectSelector } from "@/components/ProjectSelector";
import { ReportList, ReportToolbar, ReportContent } from "@/components/reports";

export default function ReportsPage() {
  const { projects } = useProjects();
  const selectedProjectId = useReportsStore((s) => s.selectedProjectId);
  const setSelectedProjectId = useReportsStore((s) => s.setSelectedProjectId);
  const reports = useReportsStore((s) => s.reports);
  const loading = useReportsStore((s) => s.loading);
  const generating = useReportsStore((s) => s.generating);
  const selectedId = useReportsStore((s) => s.selectedId);
  const setSelectedId = useReportsStore((s) => s.setSelectedId);
  const detail = useReportsStore((s) => s.detail);
  const loadingDetail = useReportsStore((s) => s.loadingDetail);
  const searchQuery = useReportsStore((s) => s.searchQuery);
  const setSearchQuery = useReportsStore((s) => s.setSearchQuery);
  const activeSection = useReportsStore((s) => s.activeSection);
  const setActiveSection = useReportsStore((s) => s.setActiveSection);
  const fetchReports = useReportsStore((s) => s.fetchReports);
  const fetchDetail = useReportsStore((s) => s.fetchDetail);
  const generate = useReportsStore((s) => s.generate);
  const exportReport = useReportsStore((s) => s.exportReport);
  const reset = useReportsStore((s) => s.reset);

  const { poll } = useJobPolling({
    onSuccess: (result) => {
      const vs = result.validation_status as string;
      const tc = (result.total_citations as number) ?? 0;
      if (vs === "valid" && result.report_id) {
        setSelectedId(String(result.report_id));
      }
      return vs === "valid"
        ? `${tc} citations, all valid`
        : `${tc} citations, some invalid`;
    },
  });

  useEffect(() => {
    if (projects.length === 1 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects]);

  useEffect(() => {
    if (selectedProjectId) {
      void fetchReports(selectedProjectId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  useEffect(() => {
    if (selectedId && selectedProjectId) {
      void fetchDetail(selectedProjectId, selectedId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // Reset store on unmount so the next visit starts fresh
  useEffect(() => {
    return () => {
      reset();
    };
  }, [reset]);

  async function handleGenerate() {
    if (!selectedProjectId) return;
    try {
      await generate(selectedProjectId, async (jobId) => {
        await poll(jobId);
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    }
  }

  async function handleExport() {
    if (!selectedProjectId || !selectedId) return;
    try {
      await exportReport(selectedProjectId, selectedId);
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
                onBack={() => setSelectedId(null)}
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
