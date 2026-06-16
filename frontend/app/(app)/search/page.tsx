"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { MagnifyingGlass, Spinner, Sparkle, ClockCounterClockwise, Lightning } from "@phosphor-icons/react";
import { useAuth } from "@/lib/stores/auth-store";
import { apiFetch } from "@/lib/api";
import { useProjects } from "@/lib/hooks/useProjects";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { PaperCard, SkeletonCard, Pagination, LanguageAudit } from "@/components/search";
import { ProjectSelector } from "@/components/ProjectSelector";
import type {
  PaperResult,
  SavePaperRequest,
  SavePaperResponse,
  SuggestQueriesResponse,
  SessionListResponse,
  SessionDetailResponse,
  SessionListItem,
} from "@/lib/types";

const PAGE_SIZE = 20;

function paperKey(paper: PaperResult) {
  return paper.semantic_scholar_id || paper.doi || paper.arxiv_id || paper.title;
}

export default function SearchPage() {
  const { token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { projects } = useProjects();

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionData, setSessionData] = useState<SessionDetailResponse | null>(null);
  const [page, setPage] = useState(1);
  const [screening, setScreening] = useState(false);
  const [autoSaving, setAutoSaving] = useState(false);
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [suggestedQueries, setSuggestedQueries] = useState<string[]>([]);
  const [suggestingLabels, setSuggestingLabels] = useState(false);

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

  const { poll: pollAutoSave } = useJobPolling({
    onSuccess: (result) => `${result.saved ?? 0} papers auto-saved`,
  });
  const { poll: pollSearch } = useJobPolling({
    onSuccess: () => "Search completed",
  });

  useEffect(() => {
    if (projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    if (sessionData?.saved_paper_ids) {
      savedIdsRef.current = new Set(sessionData.saved_paper_ids);
    }
  }, [sessionData?.saved_paper_ids]);

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
  }, [searchParams, token]);

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

  useEffect(() => {
    if (!pageLoading && sessionData) {
      requestAnimationFrame(() => { window.scrollTo({ top: 0, behavior: "smooth" }); });
    }
  }, [pageLoading, sessionData]);

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
      const data = await apiFetch<{ job_id: string; session_id: string; status: string }>("/papers/search/sessions", {
        method: "POST",
        body: JSON.stringify({ project_id: selectedProjectId, query: qs, limit: 100 }),
        headers: { Authorization: `Bearer ${token}` },
      });
      // Navigate immediately so the user sees the session
      setSessionId(data.session_id);
      router.push(`/search?session=${data.session_id}&page=1`, { scroll: false });

      toast.info("Searching papers in background...");
      const result = await pollSearch(data.job_id);
      if (result) {
        // Job completed — load session data
        const fresh = await apiFetch<SessionDetailResponse>(
          `/papers/search/sessions/${data.session_id}?page=1`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        setSessionData(fresh);
        toast.success(`Found ${fresh.total_results} papers`);
      }
      fetchSessions();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

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

  async function handleSuggestQueries() {
    if (!suggestTopic) { toast.error("Set a research question in your project first"); return; }
    setSuggestingLabels(true);
    try {
      const data = await apiFetch<SuggestQueriesResponse>("/papers/suggest-queries", {
        method: "POST",
        body: JSON.stringify({
          title: selectedProject?.title || "",
          topic: suggestTopic,
          research_question: selectedProject?.research_question || "",
        }),
        headers: { Authorization: `Bearer ${token}` },
      });
      setSuggestedQueries(data.queries);
    } catch (err) { toast.error(err instanceof Error ? err.message : "Failed to generate suggestions"); }
    finally { setSuggestingLabels(false); }
  }

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

  async function handleAutoSave() {
    if (!sessionId) return;
    setAutoSaving(true);
    try {
      const data = await apiFetch<{ job_id?: string; status?: string; total?: number; saved?: number }>(
        `/papers/search/sessions/${sessionId}/auto-save`, {
          method: "POST", headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (data.job_id && data.status === "running") {
        toast.info(`Auto-saving ${data.total} papers in background...`);
        await pollAutoSave(data.job_id);
      } else if (data.saved !== undefined) {
        toast.success(`${data.saved} papers auto-saved`);
      }
      if (sessionId) {
        const fresh = await apiFetch<SessionDetailResponse>(`/papers/search/sessions/${sessionId}?page=${page}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setSessionData(fresh);
      }
      fetchSessions();
    } catch (err) { toast.error(err instanceof Error ? err.message : "Auto-save failed"); }
    finally { setAutoSaving(false); }
  }

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
      savedIdsRef.current.add(key);
      toast.success("Paper saved");
    } catch (err) { toast.error(err instanceof Error ? err.message : "Failed to save paper"); }
    finally { setSavingId(null); }
  }

  async function handleUnsave(paper: PaperResult) {
    if (!sessionId) return;
    const key = paperKey(paper);
    setSavingId(key);
    try {
      await apiFetch(`/papers/search/sessions/${sessionId}/unsave`, {
        method: "DELETE",
        body: JSON.stringify({ semantic_scholar_id: paper.semantic_scholar_id, doi: paper.doi, arxiv_id: paper.arxiv_id }),
        headers: { Authorization: `Bearer ${token}` },
      });
      savedIdsRef.current.delete(key);
      toast.success("Paper removed from project");
    } catch (err) { toast.error(err instanceof Error ? err.message : "Failed to unsave"); }
    finally { setSavingId(null); }
  }

  function isSaved(paper: PaperResult) {
    const key = paperKey(paper);
    return savedIdsRef.current.has(key) || (sessionData?.saved_paper_ids?.includes(key) ?? false);
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <h1 className="font-display text-[40px] font-bold leading-[1.0] text-ink" style={{ letterSpacing: "-1px" }}>Search Papers</h1>
        <p className="mt-2 max-w-lg text-base leading-[1.6] text-charcoal">Search across academic databases to find papers for your literature review.</p>
      </div>

      <div className="flex items-center gap-3 mb-4">
        {projects.length > 0 && (
          <ProjectSelector projects={projects} selectedId={selectedProjectId ?? ""} onChange={setSelectedProjectId} showStatus={false} label="" />
        )}
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
            <LanguageAudit
              audit={sessionData.language_bias_audit}
              detectedLanguage={sessionData.detected_language}
              queryVariants={sessionData.query_variants}
            />
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
            {totalPages > 1 && <Pagination page={page} totalPages={totalPages} onGoPage={handleGoPage} />}
          </>
        ) : null}
      </div>
    </div>
  );
}
