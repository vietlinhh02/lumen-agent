"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  MagnifyingGlass,
  Spinner,
  User,
  Calendar,
  Buildings,
  Quotes,
  BookmarkSimple,
  CaretDown,
  ClockCounterClockwise,
  Sparkle,
  CaretLeft,
  CaretRight,
  Lightning,
} from "@phosphor-icons/react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type {
  LanguageBiasAudit,
  PaperResult,
  ProjectResponse,
  ProjectListResponse,
  QueryVariant,
  SavePaperRequest,
  SavePaperResponse,
  SuggestQueriesResponse,
  SessionListResponse,
  SessionDetailResponse,
  SessionListItem,
} from "@/lib/types";

const PAGE_SIZE = 20;

function formatAuthors(authors: Array<{ name: string; author_id?: string | null }>) {
  if (!authors || authors.length === 0) return null;
  const names = authors.map((a) => a.name);
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 3).join(", ")} et al.`;
}

function SourceBadges({ paper }: { paper: PaperResult }) {
  const badges: Array<{ label: string; className: string }> = [];
  const sourceLabels = new Set((paper.source_names || []).filter(Boolean));
  sourceLabels.forEach((source) => {
    const label = source === "semantic_scholar" ? "S2" : source.replace("_", " ");
    badges.push({ label, className: "bg-surface-bone text-charcoal" });
  });
  if (paper.arxiv_id) badges.push({ label: "arXiv", className: "bg-rose-50 text-rose-600" });
  if (paper.semantic_scholar_id && !sourceLabels.has("semantic_scholar")) {
    badges.push({ label: "S2", className: "bg-blue-50 text-blue-600" });
  }
  if (paper.is_open_access) badges.push({ label: "OA", className: "bg-emerald-50 text-emerald-600" });
  if (paper.pdf_downloaded) badges.push({ label: "PDF", className: "bg-violet-50 text-violet-600" });
  if (badges.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {badges.map((b) => (
        <span key={b.label} className={`font-ui rounded-full px-2 py-0.5 text-[10px] font-semibold ${b.className}`}>{b.label}</span>
      ))}
    </div>
  );
}

function scoreBadgeClass(score: string) {
  return { high: "bg-green-50 text-green-700", medium: "bg-amber-50 text-amber-700", low: "bg-ash/10 text-ash" }[score] || "";
}

function ProjectPicker({
  projects,
  selectedId,
  onSelect,
}: {
  projects: ProjectResponse[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);
  const selected = projects.find((p) => p.id === selectedId);
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((v) => !v)} className="focus-ring flex items-center gap-2 h-[36px] rounded-full bg-surface-bone px-4 font-ui text-[13px] font-medium text-charcoal hover:text-ink transition-colors">
        {selected ? selected.title : "Select project"} <CaretDown size={12} weight="bold" />
      </button>
      {open && (
        <div className="absolute left-0 top-[42px] z-40 w-[260px] rounded-[10px] bg-surface-card p-1 shadow-lg animate-scale-in" style={{ border: "1px solid var(--hairline)" }}>
          {projects.map((p) => (
            <button key={p.id} onClick={() => { onSelect(p.id); setOpen(false); }}
              className={`flex w-full items-center gap-2 rounded-[6px] px-3 py-2 font-ui text-[13px] transition-colors text-left ${p.id === selectedId ? "bg-surface-bone font-semibold text-ink" : "text-charcoal hover:bg-surface-bone hover:text-ink"}`}>
              <span className="truncate flex-1">{p.title}</span>
              <span className="text-ash text-[11px]">{p.paper_count}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function paperKey(paper: PaperResult) {
  return paper.semantic_scholar_id || paper.doi || paper.arxiv_id || paper.title;
}

function PaperCard({
  paper,
  projectId,
  onSave,
  onUnsave,
  saving,
  saved,
  score,
}: {
  paper: PaperResult;
  projectId: string | null;
  onSave: (paper: PaperResult) => void;
  onUnsave: (paper: PaperResult) => void;
  saving: boolean;
  saved: boolean;
  score?: string;
}) {
  const authorsStr = formatAuthors(paper.authors);
  return (
    <div className="rounded-[12px] bg-surface-card p-5 transition-all duration-200"
      style={{ border: "1px solid var(--hairline)" }}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="font-ui text-[15px] font-semibold leading-[1.4] text-ink">{paper.title}</h3>
        </div>
        <div className="flex items-center gap-1.5">
          {score && <span className={`font-ui shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${scoreBadgeClass(score)}`}>{score}</span>}
          {paper.citation_count != null && paper.citation_count > 0 && (
            <span className="font-ui shrink-0 inline-flex items-center gap-1 rounded-full bg-surface-bone px-2.5 py-1 text-[11px] font-medium text-charcoal">
              <Quotes size={11} weight="fill" />{paper.citation_count}
            </span>
          )}
        </div>
      </div>
      {authorsStr && <p className="mt-1.5 text-[13px] text-charcoal"><User size={11} className="inline align-[-2px] mr-1 text-ash" />{authorsStr}</p>}
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[12px] text-ash">
        {paper.venue && <span className="inline-flex items-center gap-1"><Buildings size={11} />{paper.venue}</span>}
        {paper.year && <span className="inline-flex items-center gap-1"><Calendar size={11} />{paper.year}</span>}
      </div>
      {paper.abstract && <p className="mt-2.5 text-[13px] leading-[1.6] text-body line-clamp-3">{paper.abstract}</p>}
      <div className="mt-3 flex items-center justify-between">
        <SourceBadges paper={paper} />
        {saved ? (
          <button onClick={() => onUnsave(paper)} disabled={saving}
            className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-green-50 px-4 text-[13px] font-semibold text-green-700 transition-all duration-200 hover:bg-red-50 hover:text-red-600 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed">
            <BookmarkSimple size={14} weight="fill" />Saved
          </button>
        ) : (
          <button onClick={() => onSave(paper)} disabled={!projectId || saving}
            className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-primary px-4 text-[13px] font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed">
            <BookmarkSimple size={14} weight="bold" />Save
          </button>
        )}
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="rounded-[12px] bg-surface-card p-5 animate-pulse" style={{ border: "1px solid var(--hairline)" }}>
      <div className="h-5 w-3/4 rounded bg-surface-bone" />
      <div className="mt-2 h-4 w-1/2 rounded bg-surface-bone" />
      <div className="mt-3 h-3 w-full rounded bg-surface-bone" />
      <div className="mt-2 h-3 w-5/6 rounded bg-surface-bone" />
      <div className="mt-3 flex justify-between">
        <div className="flex gap-1.5"><div className="h-5 w-12 rounded-full bg-surface-bone" /><div className="h-5 w-10 rounded-full bg-surface-bone" /></div>
        <div className="h-[34px] w-16 rounded-full bg-surface-bone" />
      </div>
    </div>
  );
}

export default function SearchPage() {
  const { token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);

  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionData, setSessionData] = useState<SessionDetailResponse | null>(null);
  const [page, setPage] = useState(1);
  const [screening, setScreening] = useState(false);
  const [autoSaving, setAutoSaving] = useState(false);

  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [suggestedQueries, setSuggestedQueries] = useState<string[]>([]);
  const [suggestingLabels, setSuggestingLabels] = useState(false);

  // Track saved paper IDs client-side
  const savedIdsRef = useRef<Set<string>>(new Set());

  const selectedProject = projects.find((p) => p.id === selectedProjectId);
  const suggestTopic = selectedProject?.research_question || selectedProject?.topic || null;

  const papers = (sessionData?.papers || []).map((d: any) => ({
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
    source_specific: (d.source_specific || {}) as Record<string, unknown>,
    pdf_downloaded: (d.pdf_downloaded || false) as boolean,
    pdf_path: d.pdf_path as string,
    pdf_source: d.pdf_source as string,
  })) as PaperResult[];

  const totalPages = sessionData?.total_pages || 1;
  const scores = sessionData?.screening_scores || [];

  // Sync saved IDs from backend on session load
  useEffect(() => {
    if (sessionData?.saved_paper_ids) {
      savedIdsRef.current = new Set(sessionData.saved_paper_ids);
    }
  }, [sessionData?.saved_paper_ids]);

  // Back/forward: sync state from URL when browser nav happens
  const isPopRef = useRef(false);
  useEffect(() => {
    const onPop = () => { isPopRef.current = true; };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (!isPopRef.current) return;
    isPopRef.current = false;
    const sid = searchParams.get("session");
    const p = searchParams.get("page");
    const pageNum = p ? parseInt(p, 10) : 1;
    if (!sid) return;

    setSessionId(sid);
    setPage(isNaN(pageNum) ? 1 : pageNum);
    setLoading(true);
    apiFetch<SessionDetailResponse>(`/papers/search/sessions/${sid}?page=${isNaN(pageNum) ? 1 : pageNum}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(setSessionData).catch(() => {}).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Initial mount
  useEffect(() => {
    const sid = searchParams.get("session");
    const p = parseInt(searchParams.get("page") || "1", 10);
    if (sid) {
      setSessionId(sid);
      if (!isNaN(p)) setPage(p);
      loadSessionData(sid, isNaN(p) ? 1 : p);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadSessionData(sid: string, p: number) {
    setLoading(true);
    try {
      const data = await apiFetch<SessionDetailResponse>(`/papers/search/sessions/${sid}?page=${p}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setSessionData(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load session");
    } finally {
      setLoading(false);
    }
  }

  // Scroll to top after page data renders
  useEffect(() => {
    if (!pageLoading && sessionData) {
      requestAnimationFrame(() => {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  }, [pageLoading, sessionData]);

  // Fetch projects
  const fetchProjects = useCallback(async () => {
    try {
      const data = await apiFetch<ProjectListResponse>("/projects", {
        headers: { Authorization: `Bearer ${token}` },
      });
      setProjects(data.projects);
      if (data.projects.length > 0 && !selectedProjectId) {
        setSelectedProjectId(data.projects[0].id);
      }
    } catch { /* silent */ }
  }, [token, selectedProjectId]);

  useEffect(() => { if (token) fetchProjects(); }, [token, fetchProjects]);

  // Fetch sessions
  const fetchSessions = useCallback(async () => {
    if (!selectedProjectId) return;
    try {
      const data = await apiFetch<SessionListResponse>(`/papers/search/sessions?project_id=${selectedProjectId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setSessions(data.sessions);
    } catch { /* silent */ }
  }, [token, selectedProjectId]);

  useEffect(() => { if (selectedProjectId) fetchSessions(); }, [selectedProjectId, fetchSessions]);

  // Handle search
  async function handleSearch(q?: string) {
    const qs = (q ?? query).trim();
    if (!qs || !selectedProjectId) return;
    if (q) setQuery(q);

    setLoading(true);
    setSessionId(null);
    setSessionData(null);
    setPage(1);
    savedIdsRef.current = new Set();
    try {
      const data = await apiFetch<SessionDetailResponse>("/papers/search/sessions", {
        method: "POST",
        body: JSON.stringify({ project_id: selectedProjectId, query: qs, limit: 100 }),
        headers: { Authorization: `Bearer ${token}` },
      });
      setSessionId(data.id);
      setSessionData(data);
      router.push(`/search?session=${data.id}&page=1`, { scroll: false });
      fetchSessions();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  // Load existing session
  async function handleLoadSession(sid: string) {
    setSessionId(sid);
    setPage(1);
    router.push(`/search?session=${sid}&page=1`, { scroll: false });
    setLoading(true);
    try {
      const data = await apiFetch<SessionDetailResponse>(`/papers/search/sessions/${sid}?page=1`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setSessionData(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load session");
    } finally {
      setLoading(false);
    }
  }

  // Pagination
  async function handleGoPage(p: number) {
    if (!sessionId || p < 1 || p > totalPages) return;
    setPage(p);
    setPageLoading(true);
    router.push(`/search?session=${sessionId}&page=${p}`, { scroll: false });
    try {
      const data = await apiFetch<SessionDetailResponse>(`/papers/search/sessions/${sessionId}?page=${p}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setSessionData(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load page");
    } finally {
      setPageLoading(false);
    }
  }

  // AI Suggest
  async function handleSuggestQueries() {
    if (!suggestTopic) { toast.error("Set a research question in your project first"); return; }
    setSuggestingLabels(true);
    try {
      const data = await apiFetch<SuggestQueriesResponse>("/papers/suggest-queries", {
        method: "POST", body: JSON.stringify({ topic: suggestTopic }),
        headers: { Authorization: `Bearer ${token}` },
      });
      setSuggestedQueries(data.queries);
    } catch (err) { toast.error(err instanceof Error ? err.message : "Failed to generate suggestions"); }
    finally { setSuggestingLabels(false); }
  }

  // AI Screen
  async function handleScreen() {
    if (!sessionId) { toast.error("Search first"); return; }
    setScreening(true);
    try {
      const data = await apiFetch<{ scores: string[] }>(`/papers/search/sessions/${sessionId}/screen`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` },
      });
      setSessionData((prev) => prev ? { ...prev, screening_scores: data.scores } : prev);
      toast.success(`${data.scores.filter((s) => s === "high").length} papers scored high`);
    } catch (err) { toast.error(err instanceof Error ? err.message : "Screening failed"); }
    finally { setScreening(false); }
  }

  // Auto-save high papers (async background job)
  async function handleAutoSave() {
    if (!sessionId) return;
    setAutoSaving(true);
    try {
      const data = await apiFetch<{ job_id?: string; status?: string; total?: number; saved?: number; skipped?: number; error?: string }>(
        `/papers/search/sessions/${sessionId}/auto-save`, {
          method: "POST", headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (data.job_id && data.status === "running") {
        toast.info(`Auto-saving ${data.total} papers in background...`);
        // Poll for completion
        await pollJobStatus(data.job_id);
      } else if (data.saved !== undefined) {
        toast.success(`${data.saved} papers auto-saved`);
      }

      // Refresh saved IDs
      if (sessionId) {
        const fresh = await apiFetch<SessionDetailResponse>(`/papers/search/sessions/${sessionId}?page=${page}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setSessionData(fresh);
      }
      fetchProjects();
      fetchSessions();
    } catch (err) { toast.error(err instanceof Error ? err.message : "Auto-save failed"); }
    finally { setAutoSaving(false); }
  }

  async function pollJobStatus(jobId: string) {
    const maxAttempts = 60; // 2 minutes max
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const job = await apiFetch<{ status: string; progress: number; total: number; result?: { saved: number; skipped: number }; error_message?: string }>(
          `/papers/search/jobs/${jobId}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (job.status === "completed") {
          toast.success(`${job.result?.saved ?? 0} papers auto-saved`);
          return;
        }
        if (job.status === "failed") {
          toast.error(job.error_message || "Auto-save failed");
          return;
        }
        // Update progress toast
        if (job.progress > 0) {
          toast.info(`Saved ${job.progress}/${job.total} papers...`, { autoClose: 1000 });
        }
      } catch {
        // Ignore polling errors, keep trying
      }
    }
    toast.warning("Auto-save is still running. Check back later.");
  }

  // Manual save
  async function handleSave(paper: PaperResult) {
    if (!selectedProjectId) { toast.error("Select a project first"); return; }
    const key = paperKey(paper);
    setSavingId(key);
    try {
      const body: SavePaperRequest = {
        paper_title: paper.title, paper_abstract: paper.abstract, paper_year: paper.year,
        paper_venue: paper.venue, paper_doi: paper.doi, paper_arxiv_id: paper.arxiv_id,
        paper_semantic_scholar_id: paper.semantic_scholar_id, paper_url: paper.url,
        paper_citation_count: paper.citation_count,
        paper_authors: paper.authors.map((a) => ({ name: a.name, author_id: a.author_id ?? "" })),
        paper_source_names: paper.source_names.length > 0 ? paper.source_names : ["paperhub"],
        download_pdf: true,
        source_specific: paper.source_specific,
      };
      await apiFetch<SavePaperResponse>(`/projects/${selectedProjectId}/papers`, {
        method: "POST", body: JSON.stringify(body),
        headers: { Authorization: `Bearer ${token}` },
      });
      // Mark as saved locally
      savedIdsRef.current.add(key);
      toast.success("Paper saved");
      fetchProjects();
    } catch (err) { toast.error(err instanceof Error ? err.message : "Failed to save paper"); }
    finally { setSavingId(null); }
  }

  // Unsave
  async function handleUnsave(paper: PaperResult) {
    if (!sessionId) return;
    const key = paperKey(paper);
    setSavingId(key);
    try {
      await apiFetch(`/papers/search/sessions/${sessionId}/unsave`, {
        method: "DELETE",
        body: JSON.stringify({
          semantic_scholar_id: paper.semantic_scholar_id,
          doi: paper.doi,
          arxiv_id: paper.arxiv_id,
        }),
        headers: { Authorization: `Bearer ${token}` },
      });
      savedIdsRef.current.delete(key);
      toast.success("Paper removed from project");
      fetchProjects();
    } catch (err) { toast.error(err instanceof Error ? err.message : "Failed to unsave"); }
    finally { setSavingId(null); }
  }

  function isSaved(paper: PaperResult) {
    const key = paperKey(paper);
    return savedIdsRef.current.has(key) || (sessionData?.saved_paper_ids?.includes(key) ?? false);
  }

  // Pagination UI
  function Pagination() {
    const pages: number[] = [];
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, page + 2);
    for (let i = start; i <= end; i++) pages.push(i);

    return (
      <div className="mt-6 flex items-center justify-center gap-1.5">
        <button onClick={() => handleGoPage(page - 1)} disabled={page <= 1}
          className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-surface-card text-ash hover:text-ink disabled:opacity-30 transition-colors"
          style={{ border: "1px solid var(--hairline)" }}>
          <CaretLeft size={14} />
        </button>
        {pages.map((p) => (
          <button key={p} onClick={() => handleGoPage(p)}
            className={`font-ui h-[34px] min-w-[34px] rounded-full px-2 text-[13px] font-semibold transition-all duration-200 ${
              p === page ? "bg-ink text-on-dark" : "text-charcoal hover:bg-surface-bone hover:text-ink"
            }`}>
            {p}
          </button>
        ))}
        <button onClick={() => handleGoPage(page + 1)} disabled={page >= totalPages}
          className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-surface-card text-ash hover:text-ink disabled:opacity-30 transition-colors"
          style={{ border: "1px solid var(--hairline)" }}>
          <CaretRight size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <h1 className="font-display text-[40px] font-bold leading-[1.0] text-ink" style={{ letterSpacing: "-1px" }}>Search Papers</h1>
        <p className="mt-2 max-w-lg text-base leading-[1.6] text-charcoal">Search across academic databases to find papers for your literature review.</p>
      </div>

      <div className="flex gap-3 mb-4">
        {projects.length > 0 && <ProjectPicker projects={projects} selectedId={selectedProjectId} onSelect={setSelectedProjectId} />}
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
        <div className="mb-4 flex flex-wrap gap-2 animate-slide-up">
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
        <div className="mb-4 flex items-center gap-2">
          <ClockCounterClockwise size={14} className="text-ash" />
          <div className="flex flex-wrap gap-1.5">
            {sessions.slice(0, 6).map((s) => (
              <button key={s.id} onClick={() => handleLoadSession(s.id)} disabled={loading}
                className={`font-ui rounded-full px-3 py-1 text-[12px] font-medium transition-all duration-200 ${
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
            className="focus-ring h-[48px] w-full rounded-full bg-surface-card pl-12 pr-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
            style={{ border: "1px solid var(--hairline)" }} />
          <MagnifyingGlass size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-ash" />
        </div>
        <button onClick={() => handleSearch()} disabled={loading || !query.trim()}
          className="focus-ring font-ui h-[48px] rounded-full bg-primary px-6 text-sm font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed">
          {loading ? <span className="inline-flex items-center gap-2"><Spinner size={16} className="animate-spin" weight="bold" />Searching…</span> : "Search"}
        </button>
      </div>

      {sessionData && (
        <div className="mt-4 flex items-center gap-3 flex-wrap">
          <p className="font-ui text-[13px] text-ash shrink-0">
            Found {sessionData.total_results} papers • Page {page} of {totalPages}
          </p>

          {sessionData.language_bias_audit && (
            <div className="flex items-center gap-2 text-[11px] text-ash">
              <span>·</span>
              {sessionData.detected_language && <span>{sessionData.detected_language.toUpperCase()}</span>}
              {Object.entries(sessionData.language_bias_audit.candidate_counts_by_language).map(([lang, count]) => (
                <span key={lang}>{lang.toUpperCase()}: {count}</span>
              ))}
              <span className={`font-semibold ${
                sessionData.language_bias_audit.english_dominance_score < 0.7
                  ? "text-emerald-600"
                  : sessionData.language_bias_audit.english_dominance_score < 0.85
                    ? "text-amber-600"
                    : "text-red-500"
              }`}>
                EN {Math.round(sessionData.language_bias_audit.english_dominance_score * 100)}%
              </span>
              {sessionData.query_variants && sessionData.query_variants.length > 0 && (
                <span className="relative group">
                  <span className="cursor-help border-b border-dashed border-stone">{sessionData.query_variants.length} queries</span>
                  <div className="hidden group-hover:block absolute left-0 top-full z-20 mt-1 w-[420px] rounded-lg bg-surface-card p-3 shadow-lg" style={{ border: "1px solid var(--hairline)" }}>
                    {sessionData.query_variants.map((v, i) => (
                      <div key={i} className="flex items-start gap-2 text-[11px] py-0.5">
                        <span className="font-semibold text-charcoal shrink-0">{v.source}</span>
                        <span className="text-mute break-words">{v.query}</span>
                      </div>
                    ))}
                  </div>
                </span>
              )}
            </div>
          )}

          <div className="ml-auto flex items-center gap-2">
            {scores.length > 0 ? (
              <button onClick={handleAutoSave} disabled={autoSaving}
                className="font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-green-50 px-4 text-[13px] font-semibold text-green-700 hover:bg-green-100 transition-colors disabled:opacity-50">
                <Lightning size={14} weight="fill" />
                {autoSaving ? "Saving…" : `${scores.filter((s) => s === "high").length} high · Auto-save`}
              </button>
            ) : (
              <button onClick={handleScreen} disabled={screening}
                className="font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-primary/10 px-4 text-[13px] font-semibold text-primary hover:bg-primary/20 transition-colors disabled:opacity-40">
                <Sparkle size={14} weight="fill" className={screening ? "animate-spin" : ""} />
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
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <MagnifyingGlass size={36} className="text-stone mb-3" weight="light" />
            <p className="font-ui text-sm font-semibold text-charcoal">Enter a query above to search papers</p>
          </div>
        ) : sessionData && papers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center animate-slide-up">
            <MagnifyingGlass size={40} className="text-stone mb-4" weight="light" />
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
                  projectId={selectedProjectId}
                  onSave={handleSave}
                  onUnsave={handleUnsave}
                  saving={savingId === paperKey(paper)}
                  saved={isSaved(paper)}
                  score={scores[(page - 1) * PAGE_SIZE + i]}
                />
              ))}
            </div>
            {totalPages > 1 && <Pagination />}
          </>
        ) : null}
      </div>
    </div>
  );
}
