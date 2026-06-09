"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type {
  GapResponse,
  GapListResponse,
  ConflictResponse,
  ConflictListResponse,
  ProjectListResponse,
  ProjectResponse,
} from "@/lib/types";
import {
  Lightbulb,
  Warning,
  CaretDown,
  CaretUp,
  Trash,
  ArrowCounterClockwise,
} from "@phosphor-icons/react";
import { Dropdown } from "@/components/ui/Dropdown";

export default function GapsPage() {
  const { token } = useAuth();
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [gaps, setGaps] = useState<GapResponse[]>([]);
  const [conflicts, setConflicts] = useState<ConflictResponse[]>([]);
  const [loadingGaps, setLoadingGaps] = useState(false);
  const [loadingConflicts, setLoadingConflicts] = useState(false);
  const [generatingGaps, setGeneratingGaps] = useState(false);
  const [generatingConflicts, setGeneratingConflicts] = useState(false);
  const [expandedGapId, setExpandedGapId] = useState<string | null>(null);
  const [expandedConflictId, setExpandedConflictId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"gaps" | "conflicts">("gaps");

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

  // Load gaps
  const fetchGaps = useCallback(async () => {
    if (!token || !selectedProjectId) return;
    setLoadingGaps(true);
    try {
      const data = await apiFetch<GapListResponse>(
        `/projects/${selectedProjectId}/gaps`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setGaps(data.items || []);
    } catch {
      // Silently fail — gaps may not exist yet
      setGaps([]);
    } finally {
      setLoadingGaps(false);
    }
  }, [token, selectedProjectId]);

  // Load conflicts
  const fetchConflicts = useCallback(async () => {
    if (!token || !selectedProjectId) return;
    setLoadingConflicts(true);
    try {
      const data = await apiFetch<ConflictListResponse>(
        `/projects/${selectedProjectId}/conflicts`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setConflicts(data.items || []);
    } catch {
      setConflicts([]);
    } finally {
      setLoadingConflicts(false);
    }
  }, [token, selectedProjectId]);

  useEffect(() => {
    fetchGaps();
    fetchConflicts();
  }, [fetchGaps, fetchConflicts]);

  // Generate gaps (async background job)
  async function handleGenerateGaps() {
    if (!token || !selectedProjectId) return;
    setGeneratingGaps(true);
    try {
      const result = await apiFetch<{ job_id?: string; status?: string; total?: number; error?: string }>(
        `/projects/${selectedProjectId}/gaps:generate`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        },
      );

      if (result.job_id && result.status === "running") {
        toast.info(`Analyzing ${result.total} matrix rows for gaps...`);
        await pollJob(result.job_id, "gaps");
      }

      await fetchGaps();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Generation failed",
      );
    } finally {
      setGeneratingGaps(false);
    }
  }

  // Generate conflicts (async background job)
  async function handleGenerateConflicts() {
    if (!token || !selectedProjectId) return;
    setGeneratingConflicts(true);
    try {
      const result = await apiFetch<{ job_id?: string; status?: string; total?: number; error?: string }>(
        `/projects/${selectedProjectId}/conflicts:generate`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        },
      );

      if (result.job_id && result.status === "running") {
        toast.info(`Detecting conflicts across ${result.total} matrix rows...`);
        await pollJob(result.job_id, "conflicts");
      }

      await fetchConflicts();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Generation failed",
      );
    } finally {
      setGeneratingConflicts(false);
    }
  }

  async function pollJob(jobId: string, type: "gaps" | "conflicts") {
    const maxAttempts = 60; // 2 minutes max
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const job = await apiFetch<{ status: string; progress: number; total: number; result?: { gap_count?: number; conflict_count?: number }; error_message?: string }>(
          `/papers/search/jobs/${jobId}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (job.status === "completed") {
          const count = type === "gaps" ? (job.result?.gap_count ?? 0) : (job.result?.conflict_count ?? 0);
          toast.success(type === "gaps" ? `Generated ${count} research gaps` : `Found ${count} potential conflicts`);
          return;
        }
        if (job.status === "failed") {
          toast.error(job.error_message || `${type} generation failed`);
          return;
        }
        if (job.progress > 0) {
          toast.info(`Processing ${job.progress}/${job.total}...`, { autoClose: 1000 });
        }
      } catch {
        // Ignore polling errors, keep trying
      }
    }
    toast.warning(`${type} generation is still running. Check back later.`);
  }

  // Delete gap
  async function handleDeleteGap(gapId: string) {
    if (!token || !selectedProjectId) return;
    try {
      await apiFetch(`/projects/${selectedProjectId}/gaps/${gapId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      setGaps((prev) => prev.filter((g) => g.id !== gapId));
      toast.success("Gap removed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const confidenceColor = (c: string) => {
    if (c === "high") return "bg-green-50 text-green-700";
    if (c === "low") return "bg-amber-50 text-amber-700";
    return "bg-blue-50 text-blue-700";
  };

  return (
    <div className="min-h-screen bg-canvas">
      <div className="px-4 sm:px-6 py-6">
        <div className="flex flex-col gap-6">
          {/* Header */}
          <div className="flex items-end justify-between">
            <div>
              <h1
                className="font-display text-[32px] font-bold leading-[1.0] text-ink"
                style={{ letterSpacing: "-1px" }}
              >
                Research Gaps & Conflicts
              </h1>
              <p className="mt-2 text-sm text-charcoal">
                Identify evidence-based research gaps and conflicting findings
                from your literature matrix.
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

          {/* Tabs */}
          <div className="flex gap-1 rounded-[10px] bg-surface-bone p-1 w-fit">
            <button
              onClick={() => setActiveTab("gaps")}
              className={`font-ui flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold transition-colors ${
                activeTab === "gaps"
                  ? "bg-surface-card text-ink shadow-sm"
                  : "text-charcoal hover:text-ink"
              }`}
            >
              <Lightbulb size={16} />
              Gaps ({gaps.length})
            </button>
            <button
              onClick={() => setActiveTab("conflicts")}
              className={`font-ui flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold transition-colors ${
                activeTab === "conflicts"
                  ? "bg-surface-card text-ink shadow-sm"
                  : "text-charcoal hover:text-ink"
              }`}
            >
              <Warning size={16} />
              Conflicts ({conflicts.length})
            </button>
          </div>

          {/* ── Gaps Tab ── */}
          {activeTab === "gaps" && (
            <>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleGenerateGaps}
                  disabled={!selectedProjectId || generatingGaps}
                  className="focus-ring font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
                >
                  {generatingGaps ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />
                      Generating…
                    </>
                  ) : (
                    <>
                      <Lightbulb size={16} />
                      Generate Gaps
                    </>
                  )}
                </button>
                {gaps.length > 0 && (
                  <button
                    onClick={handleGenerateGaps}
                    disabled={generatingGaps}
                    className="font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary/10 px-5 text-sm font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
                  >
                    <ArrowCounterClockwise size={16} />
                    Regenerate
                  </button>
                )}
              </div>

              {loadingGaps ? (
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
              ) : gaps.length === 0 ? (
                <div
                  className="flex flex-col items-center justify-center py-20 text-center rounded-[12px] bg-surface-card"
                  style={{ border: "1px solid var(--hairline)" }}
                >
                  <Lightbulb size={40} className="text-stone mb-4" />
                  <p className="font-ui text-base font-semibold text-ink">
                    No research gaps yet
                  </p>
                  <p className="mt-2 text-sm text-charcoal max-w-md">
                    Generate a literature matrix first, then use this tool to
                    identify evidence-based research gaps.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {gaps.map((gap) => (
                    <GapCard
                      key={gap.id}
                      gap={gap}
                      expanded={expandedGapId === gap.id}
                      onToggle={() =>
                        setExpandedGapId(
                          expandedGapId === gap.id ? null : gap.id,
                        )
                      }
                      onDelete={() => handleDeleteGap(gap.id)}
                      confidenceColor={confidenceColor}
                    />
                  ))}
                </div>
              )}
            </>
          )}

          {/* ── Conflicts Tab ── */}
          {activeTab === "conflicts" && (
            <>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleGenerateConflicts}
                  disabled={!selectedProjectId || generatingConflicts}
                  className="focus-ring font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
                >
                  {generatingConflicts ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />
                      Detecting…
                    </>
                  ) : (
                    <>
                      <Warning size={16} />
                      Detect Conflicts
                    </>
                  )}
                </button>
                {conflicts.length > 0 && (
                  <button
                    onClick={handleGenerateConflicts}
                    disabled={generatingConflicts}
                    className="font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary/10 px-5 text-sm font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
                  >
                    <ArrowCounterClockwise size={16} />
                    Redetect
                  </button>
                )}
              </div>

              {loadingConflicts ? (
                <div className="space-y-4">
                  {[1, 2].map((i) => (
                    <div
                      key={i}
                      className="rounded-[10px] bg-surface-card p-5 animate-pulse"
                      style={{ border: "1px solid var(--hairline)" }}
                    >
                      <div className="h-4 w-3/4 rounded bg-surface-bone" />
                      <div className="mt-2 h-3 w-full rounded bg-surface-bone" />
                    </div>
                  ))}
                </div>
              ) : conflicts.length === 0 ? (
                <div
                  className="flex flex-col items-center justify-center py-20 text-center rounded-[12px] bg-surface-card"
                  style={{ border: "1px solid var(--hairline)" }}
                >
                  <Warning size={40} className="text-stone mb-4" />
                  <p className="font-ui text-base font-semibold text-ink">
                    No conflicts detected
                  </p>
                  <p className="mt-2 text-sm text-charcoal max-w-md">
                    Conflicting findings are detected by comparing matrix rows
                    that share the same method or dataset but report opposing
                    results.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {conflicts.map((conflict) => (
                    <ConflictCard
                      key={conflict.id}
                      conflict={conflict}
                      expanded={expandedConflictId === conflict.id}
                      onToggle={() =>
                        setExpandedConflictId(
                          expandedConflictId === conflict.id
                            ? null
                            : conflict.id,
                        )
                      }
                      confidenceColor={confidenceColor}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Gap Card ── */

function GapCard({
  gap,
  expanded,
  onToggle,
  onDelete,
  confidenceColor,
}: {
  gap: GapResponse;
  expanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
  confidenceColor: (c: string) => string;
}) {
  return (
    <div
      className="rounded-[10px] bg-surface-card transition-shadow hover:shadow-md"
      style={{ border: "1px solid var(--hairline)" }}
    >
      {/* Header */}
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onToggle(); }}
        className="flex w-full items-start gap-3 p-5 text-left cursor-pointer"
      >
        <div className="mt-0.5 shrink-0">
          <Lightbulb size={20} className="text-amber-500" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-ui text-base font-semibold text-ink truncate">
              {gap.title}
            </h3>
            <span
              className={`font-ui shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${confidenceColor(gap.confidence)}`}
            >
              {gap.confidence}
            </span>
          </div>
          <p className="mt-1 text-sm text-charcoal line-clamp-2">
            {gap.description}
          </p>
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="flex h-[28px] w-[28px] items-center justify-center rounded-[6px] text-charcoal hover:text-error hover:bg-red-50 transition-colors"
            title="Delete gap"
          >
            <Trash size={14} />
          </button>
          {expanded ? (
            <CaretUp size={16} className="text-charcoal" />
          ) : (
            <CaretDown size={16} className="text-charcoal" />
          )}
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-[var(--hairline)] pt-4">
          {/* Suggested direction */}
          <div>
            <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-1">
              Suggested Research Direction
            </p>
            <p className="text-sm text-ink leading-relaxed">
              {gap.suggested_direction}
            </p>
          </div>

          {/* Evidence summary */}
          <div>
            <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-1">
              Evidence Summary
            </p>
            <p className="text-sm text-ink leading-relaxed">
              {gap.evidence_summary}
            </p>
          </div>

          {/* Supporting papers */}
          {gap.evidence.length > 0 && (
            <div>
              <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-2">
                Supporting Papers ({gap.evidence.length})
              </p>
              <div className="space-y-2">
                {gap.evidence.map((ev) => (
                  <div
                    key={ev.project_paper_id}
                    className="rounded-[8px] bg-surface-bone px-4 py-3"
                  >
                    <p className="font-ui text-sm font-medium text-ink">
                      {ev.title || "Unknown paper"}
                    </p>
                    <p className="mt-1 text-[12px] text-charcoal">
                      <span className="font-semibold">{ev.evidence_type}:</span>{" "}
                      {ev.note}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Conflict Card ── */

function ConflictCard({
  conflict,
  expanded,
  onToggle,
  confidenceColor,
}: {
  conflict: ConflictResponse;
  expanded: boolean;
  onToggle: () => void;
  confidenceColor: (c: string) => string;
}) {
  return (
    <div
      className="rounded-[10px] bg-surface-card transition-shadow hover:shadow-md"
      style={{ border: "1px solid var(--hairline)" }}
    >
      {/* Header */}
      <button
        onClick={onToggle}
        className="flex w-full items-start gap-3 p-5 text-left"
      >
        <div className="mt-0.5 shrink-0">
          <Warning size={20} className="text-orange-500" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-ui text-base font-semibold text-ink truncate">
              {conflict.title}
            </h3>
            <span
              className={`font-ui shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${confidenceColor(conflict.confidence)}`}
            >
              {conflict.confidence}
            </span>
          </div>
          <p className="mt-1 text-sm text-charcoal line-clamp-2">
            {conflict.description}
          </p>
        </div>
        <div className="shrink-0">
          {expanded ? (
            <CaretUp size={16} className="text-charcoal" />
          ) : (
            <CaretDown size={16} className="text-charcoal" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-[var(--hairline)] pt-4">
          {/* Shared context */}
          {conflict.shared_context && (
            <div>
              <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-1">
                Shared Context
              </p>
              <p className="text-sm text-ink">{conflict.shared_context}</p>
            </div>
          )}

          {/* Claims comparison */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="rounded-[8px] bg-green-50 px-4 py-3">
              <p className="font-ui text-[12px] font-semibold text-green-700 mb-1">
                {conflict.paper_a_title || "Paper A"}
              </p>
              <p className="text-sm text-ink">
                {conflict.claim_a || "No claim specified"}
              </p>
            </div>
            <div className="rounded-[8px] bg-red-50 px-4 py-3">
              <p className="font-ui text-[12px] font-semibold text-red-700 mb-1">
                {conflict.paper_b_title || "Paper B"}
              </p>
              <p className="text-sm text-ink">
                {conflict.claim_b || "No claim specified"}
              </p>
            </div>
          </div>

          {/* Possible explanation */}
          {conflict.possible_explanation && (
            <div>
              <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-1">
                Possible Explanation
              </p>
              <p className="text-sm text-ink leading-relaxed">
                {conflict.possible_explanation}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
