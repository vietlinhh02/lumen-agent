"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CaretDown, MagnifyingGlass, Spinner, Sparkle, ClockCounterClockwise, Lightning } from "@phosphor-icons/react";
import { useAuth } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { useSearchStore } from "@/lib/stores/search-store";
import { apiFetch } from "@/lib/api";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { AutoSearchProgress, PaperCard, SkeletonCard, Pagination, LanguageAudit, PDFPreviewModal } from "@/components/search";
import type {
  PaperResult,
} from "@/lib/types";

const PAGE_SIZE = 20;
type SearchPaperRecord = Record<string, unknown>;

function paperKey(paper: PaperResult) {
  return paper.semantic_scholar_id || paper.doi || paper.arxiv_id || paper.title;
}

export default function ProjectSearchPage() {
  const { id } = useParams<{ id: string }>();
  const token = useAuth((s) => s.token);
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = id ?? "";

  const project = useProjectsStore((s) => s.currentProject);
  const setSelectedProjectId = useSearchStore((s) => s.setSelectedProjectId);

  // Bind the search store to the active project id so all store actions
  // (search, load session, etc.) target this project.
  useEffect(() => {
    if (projectId) setSelectedProjectId(projectId);
  }, [projectId, setSelectedProjectId]);

  const query = useSearchStore((s) => s.query);
  const setQuery = useSearchStore((s) => s.setQuery);
  const loading = useSearchStore((s) => s.loading);
  const pageLoading = useSearchStore((s) => s.pageLoading);
  const savingId = useSearchStore((s) => s.savingId);
  const sessionId = useSearchStore((s) => s.sessionId);
  const sessionData = useSearchStore((s) => s.sessionData);
  const setSessionData = useSearchStore((s) => s.setSessionData);
  const page = useSearchStore((s) => s.page);
  const setPage = useSearchStore((s) => s.setPage);
  const screening = useSearchStore((s) => s.screening);
  const autoSaving = useSearchStore((s) => s.autoSaving);
  const sessions = useSearchStore((s) => s.sessions);
  const suggestedQueries = useSearchStore((s) => s.suggestedQueries);
  const suggestingLabels = useSearchStore((s) => s.suggestingLabels);

  const startSearch = useSearchStore((s) => s.startSearch);
  const loadSessions = useSearchStore((s) => s.loadSessions);
  const suggestQueries = useSearchStore((s) => s.suggestQueries);
  const screen = useSearchStore((s) => s.screen);
  const autoSave = useSearchStore((s) => s.autoSave);
  const savePaper = useSearchStore((s) => s.savePaper);
  const rejectPaper = useSearchStore((s) => s.rejectPaper);
  const unsavePaper = useSearchStore((s) => s.unsavePaper);
  const isSaved = useSearchStore((s) => s.isSaved);
  const isRejected = useSearchStore((s) => s.isRejected);
  const loadSession = useSearchStore((s) => s.loadSession);
  const loadPage = useSearchStore((s) => s.loadPage);

  const [downloadingKey, setDownloadingKey] = useState<string | null>(null);
  const [previewPaper, setPreviewPaper] = useState<PaperResult | null>(null);
  const [autoSearchMenuOpen, setAutoSearchMenuOpen] = useState(false);
  const autoSearchMenuRef = useRef<HTMLDivElement>(null);

  // Auto search state from store
  const isAutoSearching = useSearchStore((s) => s.isAutoSearching);
  const autoSearchJobId = useSearchStore((s) => s.autoSearchJobId);
  const autoSearchSessionId = useSearchStore((s) => s.autoSearchSessionId);
  const autoSearchProgressState = useSearchStore((s) => s.autoSearchProgress);
  const startAutoSearch = useSearchStore((s) => s.startAutoSearch);
  const setAutoSearchProgress = useSearchStore((s) => s.setAutoSearchProgress);
  const clearAutoSearch = useSearchStore((s) => s.clearAutoSearch);

  const papers = (sessionData?.papers || []).map((d: SearchPaperRecord) => {
    const sourceSpecific = (d.source_specific || {}) as Record<string, unknown>;
    return {
    title: d.title as string,
    abstract: (d.abstract as string) || null,
    year: d.year as number,
    venue: d.venue as string,
    doi: d.doi as string,
    arxiv_id: d.arxiv_id as string,
    semantic_scholar_id: d.semantic_scholar_id as string,
    url: d.url as string,
    citation_count: d.citation_count as number,
    authors: (d.authors || []) as Array<{ name: string; author_id?: string | null }>,
    fields_of_study: (d.fields_of_study || []) as string[],
    is_open_access: d.is_open_access as boolean,
    source_names: (d.source_names || []) as string[],
    source_specific: sourceSpecific,
    pdf_downloaded: (d.pdf_downloaded || false) as boolean,
    pdf_path: d.pdf_path as string,
    pdf_source: d.pdf_source as string,
    can_download: (d.can_download ?? Boolean(
      d.arxiv_id || sourceSpecific.pdf_url || sourceSpecific.pmc_id,
    )) as boolean,
  };
  }) as PaperResult[];

  const totalPages = sessionData?.total_pages || 1;
  const scores = sessionData?.screening_scores || [];

  const { poll: pollAutoSave } = useJobPolling({
    onSuccess: (result) => `${result.saved ?? 0} papers auto-saved`,
  });
  const { poll: pollSearch } = useJobPolling({
    onSuccess: () => "Search completed",
  });

  // ── Auto search polling ───────────────────────────────────────────────
  async function pollAutoSearchJob(jobId: string): Promise<Record<string, unknown> | null> {
    const maxAttempts = 150;
    const intervalMs = 2000;
    for (let i = 0; i < maxAttempts; i++) {
      try {
        const job = await apiFetch<{
          status: string;
          progress_json?: Record<string, unknown> | null;
          result?: Record<string, unknown>;
          error_message?: string;
        }>(`/papers/search/jobs/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (job.progress_json) {
          setAutoSearchProgress(job.progress_json as never);
        }
        if (job.status === "completed") {
          return job.result ?? {};
        }
        if (job.status === "failed") {
          return { __failed: true, error_message: job.error_message };
        }
      } catch {
        // ignore transient polling errors
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    return null;
  }

  useEffect(() => {
    if (!autoSearchJobId) return;
    let cancelled = false;
    (async () => {
      const result = await pollAutoSearchJob(autoSearchJobId);
      if (cancelled) return;
      if (!result) {
        toast.warning("Auto-search still running — check back later.");
        return;
      }
      if ((result as { __failed?: boolean }).__failed) {
        const msg = (result as { error_message?: string }).error_message || "Auto-search failed";
        toast.error(msg);
        clearAutoSearch();
        return;
      }
      const saved = (result as { saved_count?: number }).saved_count ?? 0;
      toast.success(`Auto-saved ${saved} papers`);
      // Refresh sessions list
      void loadSessions();
      clearAutoSearch();
      // Navigate to the new session (use query param — the search page
      // reads `?session=...` rather than a path segment).
      if (autoSearchSessionId && saved > 0) {
        router.push(`/projects/${projectId}/search?session=${autoSearchSessionId}&page=1`, { scroll: false });
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSearchJobId]);

  // Click-outside handler for auto search dropdown
  useEffect(() => {
    if (!autoSearchMenuOpen) return;
    function onDown(e: MouseEvent) {
      if (autoSearchMenuRef.current && !autoSearchMenuRef.current.contains(e.target as Node)) {
        setAutoSearchMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [autoSearchMenuOpen]);

  // Re-sync URL -> store on initial mount so refresh keeps the session.
  useEffect(() => {
    const sid = searchParams.get("session");
    const p = parseInt(searchParams.get("page") || "1", 10);
    if (sid && (!sessionId || sessionId !== sid)) {
      void loadSession(sid, isNaN(p) ? 1 : p);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load previous search sessions for this project
  useEffect(() => {
    if (projectId) void loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (!pageLoading && sessionData) {
      requestAnimationFrame(() => { window.scrollTo({ top: 0, behavior: "smooth" }); });
    }
  }, [pageLoading, sessionData]);

  async function handleSearch(q?: string) {
    const qs = (q ?? query).trim();
    if (!qs || !projectId) return;
    if (q) setQuery(q);
    try {
      const data = await startSearch(qs);
      if (!data) return;
      const baseUrl = `/projects/${projectId}/search`;
      router.push(`${baseUrl}?session=${data.session_id}&page=1`, { scroll: false });
      toast.info("Searching papers in background...");
      const result = await pollSearch(data.job_id);
      if (result) {
        await loadSession(data.session_id, 1);
        const fresh = useSearchStore.getState().sessionData;
        if (fresh) toast.success(`Found ${fresh.total_results} papers`);
      }
      await loadSessions();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Search failed");
    }
  }

  async function handleLoadSession(sid: string) {
    router.push(`/projects/${projectId}/search?session=${sid}&page=1`, { scroll: false });
    await loadSession(sid, 1);
  }

  async function handleGoPage(p: number) {
    if (!sessionId || p < 1 || p > totalPages) return;
    setPage(p);
    router.push(`/projects/${projectId}/search?session=${sessionId}&page=${p}`, { scroll: false });
    await loadPage(p);
  }

  async function handleSuggestQueries() {
    if (!project) { toast.error("Project not loaded"); return; }
    await suggestQueries({
      title: project.title,
      topic: project.research_question || project.topic,
      research_question: project.research_question || "",
    });
  }

  async function handleScreen() {
    if (!sessionId) { toast.error("Search first"); return; }
    try {
      await screen();
      const fresh = useSearchStore.getState().sessionData;
      if (fresh) {
        toast.success(`${fresh.screening_scores?.filter((s) => s === "high").length ?? 0} papers scored high`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Screening failed");
    }
  }

  async function handleAutoSave() {
    if (!sessionId) return;
    try {
      await autoSave(async (jobId) => {
        const result = await pollAutoSave(jobId);
        return result;
      });
      toast.success("Auto-save complete");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Auto-save failed");
    }
  }

  async function handleAutoSearch(targetCount: 5 | 15 | 25) {
    if (!projectId) return;
    setAutoSearchMenuOpen(false);
    const trimmed = query.trim();
    try {
      await startAutoSearch(trimmed, projectId, targetCount);
      const msg = trimmed
        ? `Auto-searching for top ${targetCount} papers…`
        : `AI is generating a query, then searching for top ${targetCount} papers…`;
      toast.info(msg, { duration: 3000 });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Auto-search failed";
      if (msg.includes("429")) {
        toast.warning("Another auto-search is already running");
      } else {
        toast.error(msg);
      }
    }
  }

  async function handleSave(paper: PaperResult) {
    if (!projectId) return;
    const result = await savePaper(paper, projectId);
    if (result) toast.success("Paper saved");
    else toast.error("Failed to save paper");
  }

  async function handleReject(paper: PaperResult, exclusionReason: string) {
    if (!projectId) return;
    const result = await rejectPaper(paper, projectId, exclusionReason);
    if (result) toast.success("Paper rejected with reason");
    else toast.error("Failed to reject paper");
  }

  async function handleUnsave(paper: PaperResult) {
    const ok = await unsavePaper(paper);
    if (ok) toast.success("Paper removed from project");
    else toast.error("Failed to unsave");
  }

  async function handleDownloadPDF(paper: PaperResult) {
    if (!sessionId) { toast.error("Open a search session first"); return; }
    const key = paperKey(paper);
    setDownloadingKey(key);
    try {
      const data = await apiFetch<{
        ok: boolean;
        paper?: SearchPaperRecord;
        error?: string;
        already_downloaded?: boolean;
      }>(
        `/papers/search/sessions/${sessionId}/download-pdf`,
        {
          method: "POST",
          body: JSON.stringify({
            semantic_scholar_id: paper.semantic_scholar_id,
            doi: paper.doi,
            arxiv_id: paper.arxiv_id,
            title: paper.title,
          }),
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      if (data?.ok && data.paper) {
        const downloadedPaper = data.paper;
        // Patch the matching paper in-place so the card flips to "View"
        // immediately. We read the current session via the store to avoid
        // depending on a functional updater.
        const current = useSearchStore.getState().sessionData;
        if (current) {
          const updated = (current.papers || []).map((p: SearchPaperRecord) => {
            const same =
              (downloadedPaper.semantic_scholar_id &&
                p.semantic_scholar_id === downloadedPaper.semantic_scholar_id) ||
              (downloadedPaper.doi && p.doi === downloadedPaper.doi) ||
              (downloadedPaper.arxiv_id && p.arxiv_id === downloadedPaper.arxiv_id) ||
              (downloadedPaper.title && p.title === downloadedPaper.title);
            return same ? { ...p, ...downloadedPaper } : p;
          });
          setSessionData({ ...current, papers: updated });
        }
        toast.success("PDF downloaded");
      } else if (data?.error) {
        toast.error(data.error);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "PDF download failed");
    } finally {
      setDownloadingKey(null);
    }
  }

  function handlePreview(paper: PaperResult) {
    if (!paper.pdf_downloaded || !paper.pdf_path) {
      toast.error("PDF not downloaded yet");
      return;
    }
    setPreviewPaper(paper);
  }

  const suggestTopic = project?.research_question || project?.topic || null;

  return (
    <div>
      <div className="mb-4">
        <h2 className="font-display text-[22px] font-bold leading-[1.0] text-ink">
          Search Papers
        </h2>
        <p className="mt-1 font-ui text-[12px] text-charcoal">
          Search academic databases and save papers to <span className="font-semibold">{project?.title}</span>.
        </p>
      </div>

      <div className="flex items-center gap-3 mb-3">
        {suggestTopic && (
          <button onClick={handleSuggestQueries} disabled={suggestingLabels}
            className={`focus-ring flex shrink-0 items-center gap-1.5 h-[36px] rounded-full px-3.5 font-ui text-[13px] font-medium transition-all duration-200 ${
              suggestedQueries.length > 0 ? "bg-surface-bone text-charcoal hover:text-ink" : "bg-primary/10 text-primary hover:bg-primary/20"}`}>
            <Sparkle size={14} weight="fill" className={suggestingLabels ? "animate-spin" : ""} />
            {suggestingLabels ? "Thinking…" : suggestedQueries.length > 0 ? "Regenerate" : "AI Suggest"}
          </button>
        )}
      </div>

      {suggestedQueries.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2 animate-slide-up">
          {suggestedQueries.map((q, i) => (
            <button key={i} onClick={() => handleSearch(q)} disabled={loading}
              className="font-ui inline-flex items-center gap-1.5 rounded-full bg-surface-card px-3.5 py-1.5 text-[12px] font-medium text-charcoal hover:text-ink hover:bg-surface-bone transition-all duration-200"
              style={{ border: "1px solid var(--hairline)" }}>
              <MagnifyingGlass size={11} className="text-ash" />{q}
            </button>
          ))}
        </div>
      )}

      {sessions.length > 0 && (
        <div className="mb-3 flex items-center gap-2 overflow-x-auto scrollbar-hide">
          <ClockCounterClockwise size={14} className="text-ash shrink-0" />
          <div className="flex flex-nowrap gap-1.5">
            {sessions.slice(0, 6).map((s) => (
              <button key={s.id} onClick={() => handleLoadSession(s.id)} disabled={loading}
                className={`font-ui shrink-0 rounded-full px-3 py-1 text-[12px] font-medium transition-all duration-200 ${
                  sessionId === s.id ? "bg-ink/10 text-ink" : "text-ash hover:text-charcoal hover:bg-surface-bone"
                }`}>
                {s.user_query.length > 35 ? s.user_query.slice(0, 35) + "…" : s.user_query}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <div className="flex-1 relative">
          <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
            placeholder="e.g. transformer models for medical image segmentation"
            className="focus-ring h-[44px] w-full rounded-full bg-surface-card pl-12 pr-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
            style={{ border: "1px solid var(--hairline)" }} />
          <MagnifyingGlass size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-ash" />
        </div>
        <button onClick={() => handleSearch()} disabled={loading || !query.trim()}
          className="focus-ring font-ui h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed">
          {loading ? <span className="inline-flex items-center gap-2"><Spinner size={14} className="animate-spin" weight="bold" />Searching…</span> : "Search"}
        </button>

        {/* Auto Search dropdown */}
        <div className="relative" ref={autoSearchMenuRef}>
          <button
            disabled={loading || isAutoSearching || !projectId}
            onClick={() => setAutoSearchMenuOpen((v) => !v)}
            className="focus-ring font-ui h-[44px] inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-5 text-sm font-semibold text-primary hover:bg-primary/20 transition-all duration-200 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Sparkle size={14} weight="fill" />
            {isAutoSearching ? "Auto-searching…" : "Auto Search"}
            <CaretDown size={12} weight="bold" />
          </button>
          {autoSearchMenuOpen && (
            <div className="absolute right-0 mt-2 w-56 rounded-xl border border-hairline bg-surface-card shadow-lg z-10 overflow-hidden">
              {([5, 15, 25] as const).map((n) => (
                <button
                  key={n}
                  onClick={() => handleAutoSearch(n)}
                  className="block w-full text-left px-4 py-2.5 text-[13px] text-ink hover:bg-surface-bone transition-colors"
                >
                  Auto Search {n} papers
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Auto search progress */}
      {(isAutoSearching || autoSearchProgressState || autoSearchJobId) && (
        <div className="mt-3">
          <AutoSearchProgress
            progress={autoSearchProgressState}
            isDone={!!(autoSearchProgressState && (autoSearchProgressState.phase === "done"))}
            isFailed={!!(autoSearchProgressState && (autoSearchProgressState.phase === "failed"))}
            errorMessage={autoSearchProgressState?.error ?? null}
          />
        </div>
      )}

      {sessionData && (
        <div className="mt-3 flex items-center gap-3 flex-wrap">
          <p className="font-ui text-[12px] text-ash shrink-0">
            Found {sessionData.total_results} papers · Page {page} of {totalPages}
          </p>
          {sessionData.language_bias_audit && (
            <LanguageAudit
              audit={sessionData.language_bias_audit}
              detectedLanguage={sessionData.detected_language}
              queryVariants={sessionData.query_variants}
            />
          )}
          <div className="ml-auto flex items-center gap-2">
            {scores.length > 0 ? (
              <button onClick={handleAutoSave} disabled={autoSaving}
                className="font-ui inline-flex items-center gap-1.5 h-[32px] rounded-full bg-green-50 px-4 text-[12px] font-semibold text-green-700 hover:bg-green-100 transition-colors disabled:opacity-50">
                <Lightning size={13} weight="fill" />
                {autoSaving ? "Saving…" : `${Math.min(scores.filter((s) => s === "high").length, 25)} high · Auto-save`}
              </button>
            ) : (
              <button onClick={handleScreen} disabled={screening}
                className="font-ui inline-flex items-center gap-1.5 h-[32px] rounded-full bg-primary/10 px-4 text-[12px] font-semibold text-primary hover:bg-primary/20 transition-colors disabled:opacity-40">
                <Sparkle size={13} weight="fill" className={screening ? "animate-spin" : ""} />
                {screening ? "Screening…" : "AI Screen"}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="mt-4">
        {(loading || pageLoading) ? (
          <div className="space-y-3">{[0, 1, 2, 3, 4].map((i) => <SkeletonCard key={i} />)}</div>
        ) : !sessionId && !loading ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <MagnifyingGlass size={32} className="text-stone mb-3" weight="light" />
            <p className="font-ui text-[13px] font-semibold text-charcoal">Enter a query above to search papers</p>
          </div>
        ) : sessionData && papers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center animate-slide-up">
            <MagnifyingGlass size={36} className="text-stone mb-4" weight="light" />
            <p className="font-ui text-base font-semibold text-ink">No results found</p>
            <p className="mt-2 text-sm text-charcoal">Try a different query or broader terms.</p>
          </div>
        ) : sessionData ? (
          <>
            <div className="space-y-3">
              {papers.map((paper, i) => (
                <PaperCard
                  key={paperKey(paper) || `${paper.title}-${i}`}
                  paper={paper}
                  projectId={projectId}
                  onSave={handleSave}
                  onReject={handleReject}
                  onUnsave={handleUnsave}
                  onDownload={handleDownloadPDF}
                  onPreview={handlePreview}
                  saving={savingId === paperKey(paper)}
                  savingPdf={downloadingKey === paperKey(paper)}
                  saved={isSaved(paper)}
                  rejected={isRejected(paper)}
                  score={scores[(page - 1) * PAGE_SIZE + i]}
                />
              ))}
            </div>
            {totalPages > 1 && <Pagination page={page} totalPages={totalPages} onGoPage={handleGoPage} />}
          </>
        ) : null}
      </div>

      {previewPaper && previewPaper.pdf_path && (
        <PDFPreviewModal
          paper={previewPaper}
          pdfUrl={previewPaper.pdf_path}
          isOpen={!!previewPaper}
          onClose={() => setPreviewPaper(null)}
        />
      )}
    </div>
  );
}
