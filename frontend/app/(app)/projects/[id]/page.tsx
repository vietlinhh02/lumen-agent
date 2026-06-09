"use client";

import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import { CaretLeft, FileText, DotsThree, PencilSimple, Trash } from "@phosphor-icons/react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type { ProjectResponse, ProjectPaperResponse, FullTextResponse, NormalizeResponse } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { PaperCard } from "@/components/PaperCard";
import { EditProjectModal } from "@/components/EditProjectModal";
import { DeleteProjectModal } from "@/components/DeleteProjectModal";
import { ManualDownloadModal } from "@/components/ManualDownloadModal";
import { FullTextPanel } from "@/components/FullTextPanel";

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const router = useRouter();
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [papers, setPapers] = useState<ProjectPaperResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [downloadingPaperId, setDownloadingPaperId] = useState<string | null>(null);
  const [removingPaperId, setRemovingPaperId] = useState<string | null>(null);
  const [manualDownloadPaperId, setManualDownloadPaperId] = useState<string | null>(null);
  const [fullTextPaperId, setFullTextPaperId] = useState<string | null>(null);
  const [fullTextData, setFullTextData] = useState<FullTextResponse | null>(null);
  const [normalizing, setNormalizing] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const fetchData = useCallback(async () => {
    try {
      const result = await apiFetch<ProjectResponse>(`/projects/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setProject(result);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load project");
    }
  }, [id, token]);

  const fetchPapers = useCallback(async () => {
    try {
      const data = await apiFetch<ProjectPaperResponse[]>(`/projects/${id}/papers`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setPapers(Array.isArray(data) ? data : []);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load papers");
    } finally {
      setLoading(false);
    }
  }, [id, token]);

  async function handleDownloadPDF(projectPaperId: string) {
    setDownloadingPaperId(projectPaperId);
    try {
      const updatedPaper = await apiFetch<ProjectPaperResponse>(
        `/projects/${id}/papers/${projectPaperId}/download-pdf`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      toast.success("PDF downloaded successfully");
      setPapers((prev) =>
        prev.map((p) => (p.id === projectPaperId ? updatedPaper : p))
      );
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
      setPapers((prev) => prev.filter((paper) => paper.id !== projectPaperId));
      setProject((prev) =>
        prev ? { ...prev, paper_count: Math.max(0, prev.paper_count - 1) } : prev
      );
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
        }
      );
      toast.success("PDF downloaded successfully using custom link");
      setPapers((prev) =>
        prev.map((p) => (p.id === paperId ? updatedPaper : p))
      );
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
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setFullTextData(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load full text");
      setFullTextPaperId(null);
    }
  }

  async function handleNormalizeAll() {
    setNormalizing(true);
    try {
      const result = await apiFetch<NormalizeResponse>(
        `/projects/${id}/papers:normalize`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      toast.info(`Normalization started — ${result.skipped} paper(s) processing in background. Refresh in a moment.`);
      // Poll for completion
      const pollInterval = setInterval(async () => {
        await fetchPapers();
      }, 5000);
      setTimeout(() => clearInterval(pollInterval), 120000);
      fetchPapers();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to process papers");
    } finally {
      setNormalizing(false);
    }
  }

  useEffect(() => {
    fetchData();
    fetchPapers();
  }, [fetchData, fetchPapers]);

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="mb-8">
          <div className="h-5 w-20 rounded bg-surface-bone animate-pulse" />
          <div className="mt-3 h-10 w-1/2 rounded bg-surface-bone animate-pulse" />
          <div className="mt-2 h-5 w-1/3 rounded bg-surface-bone animate-pulse" />
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="rounded-[10px] bg-surface-card p-5 animate-pulse"
              style={{ border: "1px solid var(--hairline)" }}
            >
              <div className="h-4 w-3/4 rounded bg-surface-bone" />
              <div className="mt-2 h-3 w-full rounded bg-surface-bone" />
              <div className="mt-2 h-3 w-5/6 rounded bg-surface-bone" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center animate-fade-in">
        <p className="font-ui text-lg font-semibold text-ink">Project not found</p>
        <Link
          href="/projects"
          className="font-ui mt-4 text-sm font-semibold text-primary hover:text-primary-deep underline underline-offset-2"
        >
          ← Back to Projects
        </Link>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <Link
        href="/projects"
        className="font-ui inline-flex items-center gap-1 text-sm font-semibold text-charcoal hover:text-ink transition-colors mb-6"
      >
        <CaretLeft size={14} weight="bold" />
        Back to Projects
      </Link>

      <div className="mb-10">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h1
              className="font-display text-[36px] font-bold leading-[1.0] text-ink"
              style={{ letterSpacing: "-1px" }}
            >
              {project.title}
            </h1>
            <p className="mt-2 text-base leading-[1.5] text-charcoal">{project.topic}</p>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`font-ui shrink-0 rounded-full px-3 py-1 text-[12px] font-semibold ${
                project.status === "active"
                  ? "bg-green-50 text-green-700"
                  : "bg-ash/10 text-ash"
              }`}
            >
              {project.status === "active" ? "Active" : "Archived"}
            </span>

            <div ref={menuRef} className="relative">
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="flex h-[32px] w-[32px] items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
              >
                <DotsThree size={20} weight="bold" />
              </button>

              {menuOpen && (
                <div
                  className="absolute right-0 top-[40px] z-40 w-[160px] rounded-[10px] bg-surface-card p-1 shadow-lg animate-scale-in"
                  style={{ border: "1px solid var(--hairline)" }}
                >
                  <button
                    onClick={() => { setMenuOpen(false); setEditOpen(true); }}
                    className="flex w-full items-center gap-2 rounded-[6px] px-3 py-2 font-ui text-[13px] font-medium text-ink hover:bg-surface-bone transition-colors"
                  >
                    <PencilSimple size={14} />
                    Edit
                  </button>
                  <button
                    onClick={() => { setMenuOpen(false); setDeleteOpen(true); }}
                    className="flex w-full items-center gap-2 rounded-[6px] px-3 py-2 font-ui text-[13px] font-medium text-error hover:bg-red-50 transition-colors"
                  >
                    <Trash size={14} />
                    Delete
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {project.research_question && (
          <p className="mt-3 text-base leading-[1.6] text-body">
            {project.research_question}
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 font-ui text-[13px] text-ash">
          <span>{project.paper_count} papers saved</span>
          <span>Updated {formatDate(project.updated_at)}</span>
          <span>Created {formatDate(project.created_at)}</span>
        </div>
      </div>

      <div className="mb-6 flex items-end justify-between">
        <h2 className="font-display text-[24px] font-bold leading-[1.0] text-ink">
          Papers
        </h2>
        <span className="font-ui text-sm text-ash">{papers.length} total</span>
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
          <button
            onClick={() => router.push("/search")}
            className="focus-ring font-ui mt-6 inline-flex items-center gap-2 h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep active:bg-primary-deep"
          >
            Search Papers
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {papers.some((p) => p.full_text_status === "raw_extracted") && (
            <div className="flex justify-end">
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

      {editOpen && (
        <EditProjectModal
          project={project}
          token={token}
          onClose={() => setEditOpen(false)}
          onSaved={(updated) => setProject(updated)}
        />
      )}

      {deleteOpen && (
        <DeleteProjectModal
          projectId={project.id}
          token={token}
          onClose={() => setDeleteOpen(false)}
          onDeleted={() => router.push("/projects")}
        />
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
