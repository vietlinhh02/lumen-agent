"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { FileText } from "@phosphor-icons/react";
import { useAuth } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { apiFetch } from "@/lib/api";
import type { ProjectPaperResponse, FullTextResponse, NormalizeResponse } from "@/lib/types";
import { PaperCard } from "@/components/PaperCard";
import { ManualDownloadModal } from "@/components/ManualDownloadModal";
import { FullTextPanel } from "@/components/FullTextPanel";

export default function ProjectPapersPage() {
  const { id } = useParams<{ id: string }>();
  const token = useAuth((s) => s.token);
  const papers = useProjectsStore((s) => s.currentPapers);
  const fetchProjectPapers = useProjectsStore((s) => s.fetchProjectPapers);

  const [downloadingPaperId, setDownloadingPaperId] = useState<string | null>(null);
  const [removingPaperId, setRemovingPaperId] = useState<string | null>(null);
  const [manualDownloadPaperId, setManualDownloadPaperId] = useState<string | null>(null);
  const [fullTextPaperId, setFullTextPaperId] = useState<string | null>(null);
  const [fullTextData, setFullTextData] = useState<FullTextResponse | null>(null);
  const [normalizing, setNormalizing] = useState(false);
  const [normalizeProgress, setNormalizeProgress] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      void fetchProjectPapers(id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const hasInProgressPaper = papers.some(
    (p) => p.full_text_status === "pending" || p.full_text_status === "normalizing",
  );

  useEffect(() => {
    if (!id || !hasInProgressPaper || normalizing) return;
    const interval = setInterval(() => {
      if (id) void fetchProjectPapers(id);
    }, 2500);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, hasInProgressPaper, normalizing]);

  async function handleDownloadPDF(projectPaperId: string) {
    setDownloadingPaperId(projectPaperId);
    try {
      const updatedPaper = await apiFetch<ProjectPaperResponse>(
        `/projects/${id}/papers/${projectPaperId}/download-pdf`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      toast.success("PDF downloaded successfully");
      if (id) void fetchProjectPapers(id);
      void updatedPaper;
    } catch {
      setManualDownloadPaperId(projectPaperId);
    } finally {
      setDownloadingPaperId(null);
    }
  }

  async function handleRemovePaper(projectPaperId: string) {
    setRemovingPaperId(projectPaperId);
    try {
      await apiFetch(`/projects/${id}/papers/${projectPaperId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (id) void fetchProjectPapers(id);
      toast.success("Paper removed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to remove paper");
    } finally {
      setRemovingPaperId(null);
    }
  }

  async function handleManualDownloadSubmit(url: string) {
    if (!manualDownloadPaperId) return;
    const paperId = manualDownloadPaperId;
    setManualDownloadPaperId(null);
    setDownloadingPaperId(paperId);
    try {
      const updatedPaper = await apiFetch<ProjectPaperResponse>(
        `/projects/${id}/papers/${paperId}/download-pdf?pdf_url=${encodeURIComponent(url.trim())}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      toast.success("PDF downloaded successfully using custom link");
      void updatedPaper;
      if (id) void fetchProjectPapers(id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to download custom PDF link");
    } finally {
      setDownloadingPaperId(null);
    }
  }

  async function handleViewFullText(projectPaperId: string) {
    setFullTextPaperId(projectPaperId);
    setFullTextData(null);
    try {
      const data = await apiFetch<FullTextResponse>(
        `/projects/${id}/papers/${projectPaperId}/full-text`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setFullTextData(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load full text");
      setFullTextPaperId(null);
    }
  }

  async function handleNormalizeAll() {
    setNormalizing(true);
    setNormalizeProgress("Starting...");
    try {
      const result = await apiFetch<NormalizeResponse>(
        `/projects/${id}/papers:normalize`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      const totalPapers = result.skipped;
      setNormalizeProgress(`Processing 0/${totalPapers}...`);
      toast.info(`Normalization started — ${totalPapers} paper(s) queued.`);

      const pollInterval = setInterval(async () => {
        try {
          if (!id) return;
          const data = await apiFetch<ProjectPaperResponse[]>(`/projects/${id}/papers`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          const fresh = Array.isArray(data) ? data : [];
          useProjectsStore.setState({ currentPapers: fresh });

          const raw = fresh.filter(
            (p) => p.full_text_status === "raw_extracted" || p.full_text_status === "normalizing",
          ).length;
          const done = fresh.filter((p) => p.full_text_status === "completed").length;
          const failed = fresh.filter((p) => p.full_text_status === "failed").length;
          const processed = done + failed;

          if (raw === 0) {
            clearInterval(pollInterval);
            setNormalizing(false);
            setNormalizeProgress(null);
            if (failed > 0) {
              toast.warning(`Processing complete: ${done} succeeded, ${failed} failed`);
            } else {
              toast.success(`All ${done} papers processed successfully`);
            }
          } else {
            setNormalizeProgress(
              `Processing ${processed}/${totalPapers} (${raw} remaining${failed > 0 ? `, ${failed} failed` : ""})`,
            );
          }
        } catch {
          // ignore
        }
      }, 4000);

      setTimeout(() => {
        clearInterval(pollInterval);
        setNormalizing(false);
        setNormalizeProgress(null);
        if (id) void fetchProjectPapers(id);
      }, 600000);

      if (id) void fetchProjectPapers(id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to process papers");
      setNormalizing(false);
      setNormalizeProgress(null);
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-end justify-between">
        <div>
          <h2 className="font-display text-[22px] font-bold leading-[1.0] text-ink">
            Papers
          </h2>
          <p className="mt-1 font-ui text-[12px] text-charcoal">
            {papers.length} paper{papers.length !== 1 ? "s" : ""} in this project
          </p>
        </div>
      </div>

      {papers.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center py-20 text-center rounded-[12px] bg-surface-card"
          style={{ border: "1px solid var(--hairline)" }}
        >
          <FileText size={40} className="text-stone mb-4" />
          <p className="font-ui text-base font-semibold text-ink">No papers yet</p>
          <p className="mt-2 text-sm text-charcoal">
            Search and save papers to this project to start your literature review.
          </p>
          <a
            href={`/projects/${id}/search`}
            className="focus-ring font-ui mt-6 inline-flex items-center gap-2 h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep active:bg-primary-deep"
          >
            Search Papers
          </a>
        </div>
      ) : (
        <div className="space-y-3">
          {(papers.some((p) => p.full_text_status === "raw_extracted") || normalizing) && (
            <div className="flex items-center justify-end gap-3">
              {normalizeProgress && (
                <span className="font-ui text-[12px] text-ash">{normalizeProgress}</span>
              )}
              <button
                onClick={handleNormalizeAll}
                disabled={normalizing}
                className="font-ui inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-2 text-[12px] font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
              >
                {normalizing ? "Processing…" : "Process All with LLM"}
              </button>
            </div>
          )}
          {papers.map((paper) => (
            <PaperCard
              key={paper.id}
              paper={paper}
              onDownload={() => handleDownloadPDF(paper.id)}
              onRemove={() => handleRemovePaper(paper.id)}
              onViewFullText={() => handleViewFullText(paper.id)}
              downloading={downloadingPaperId === paper.id}
              removing={removingPaperId === paper.id}
            />
          ))}
        </div>
      )}

      {manualDownloadPaperId && (
        <ManualDownloadModal
          onClose={() => setManualDownloadPaperId(null)}
          onSubmit={handleManualDownloadSubmit}
        />
      )}

      {fullTextPaperId && fullTextData && (
        <FullTextPanel
          data={fullTextData}
          onClose={() => { setFullTextPaperId(null); setFullTextData(null); }}
        />
      )}
    </div>
  );
}
