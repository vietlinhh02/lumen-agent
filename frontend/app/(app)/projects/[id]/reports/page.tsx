"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import { toast } from "sonner";
import { PencilLine } from "@phosphor-icons/react";
import { useReportsStore } from "@/lib/stores/reports-store";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { parseSections, buildToc } from "@/lib/markdown";
import { ReportList, ReportToolbar, ReportContent } from "@/components/reports";

export default function ProjectReportsPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ?? "";

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

  const { poll } = useJobPolling({
    onProgress: (progress, total, details) => {
      // Return a string to show in toast, or use store to show inline
      if (details?.current) {
        return `Generating section: ${details.current}`;
      }
      return "Generating literature review...";
    },
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
    if (projectId) setSelectedProjectId(projectId);
  }, [projectId, setSelectedProjectId]);

  useEffect(() => {
    if (!projectId) return;
    void fetchReports(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (selectedId && projectId) {
      void fetchDetail(projectId, selectedId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  async function handleGenerate() {
    if (!projectId) return;
    try {
      await generate(projectId, async (jobId) => {
        await poll(jobId);
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    }
  }

  async function handleExport() {
    if (!projectId || !selectedId) return;
    try {
      await exportReport(projectId, selectedId);
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
    <div className="flex flex-col" style={{ height: "calc(100vh - 220px)" }}>
      <div className="mb-3 shrink-0">
        <h2 className="font-display text-[22px] font-bold leading-[1.0] text-ink">
          Literature Reviews
        </h2>
        <p className="mt-1 font-ui text-[12px] text-charcoal">
          Citation-safe reviews generated from the literature matrix.
        </p>
      </div>

      <div
        className="rounded-[14px] bg-surface-card overflow-hidden flex-1 min-h-0"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <div className="flex h-full min-h-0">
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
                <p className="mt-1 font-ui text-[12px] text-ash">Or generate a new one.</p>
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
    </div>
  );
}
