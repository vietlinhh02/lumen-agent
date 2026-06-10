"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Lightbulb, Warning, ArrowCounterClockwise } from "@phosphor-icons/react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { useProjects } from "@/lib/hooks/useProjects";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { ProjectSelector } from "@/components/ProjectSelector";
import { GapCard, ConflictCard } from "@/components/gaps";
import type { GapResponse, GapListResponse, ConflictResponse, ConflictListResponse } from "@/lib/types";

const confidenceColor = (c: string) => {
  if (c === "high") return "bg-green-50 text-green-700";
  if (c === "low") return "bg-amber-50 text-amber-700";
  return "bg-blue-50 text-blue-700";
};

export default function GapsPage() {
  const { token } = useAuth();
  const { projects } = useProjects();
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

  const { poll: pollGaps } = useJobPolling({
    onSuccess: (result) => `Generated ${result.gap_count ?? 0} research gaps`,
  });
  const { poll: pollConflicts } = useJobPolling({
    onSuccess: (result) => `Found ${result.conflict_count ?? 0} potential conflicts`,
  });

  useEffect(() => {
    if (projects.length === 1) setSelectedProjectId(projects[0].id);
  }, [projects]);

  const fetchGaps = useCallback(async () => {
    if (!token || !selectedProjectId) return;
    setLoadingGaps(true);
    try {
      const data = await apiFetch<GapListResponse>(`/projects/${selectedProjectId}/gaps`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setGaps(data.items || []);
    } catch {
      setGaps([]);
    } finally {
      setLoadingGaps(false);
    }
  }, [token, selectedProjectId]);

  const fetchConflicts = useCallback(async () => {
    if (!token || !selectedProjectId) return;
    setLoadingConflicts(true);
    try {
      const data = await apiFetch<ConflictListResponse>(`/projects/${selectedProjectId}/conflicts`, {
        headers: { Authorization: `Bearer ${token}` },
      });
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

  async function handleGenerateGaps() {
    if (!token || !selectedProjectId) return;
    setGeneratingGaps(true);
    try {
      const result = await apiFetch<{ job_id?: string; status?: string; total?: number }>(
        `/projects/${selectedProjectId}/gaps:generate`,
        { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } },
      );
      if (result.job_id && result.status === "running") {
        toast.info(`Analyzing ${result.total} matrix rows for gaps...`);
        await pollGaps(result.job_id);
      }
      await fetchGaps();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGeneratingGaps(false);
    }
  }

  async function handleGenerateConflicts() {
    if (!token || !selectedProjectId) return;
    setGeneratingConflicts(true);
    try {
      const result = await apiFetch<{ job_id?: string; status?: string; total?: number }>(
        `/projects/${selectedProjectId}/conflicts:generate`,
        { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } },
      );
      if (result.job_id && result.status === "running") {
        toast.info(`Detecting conflicts across ${result.total} matrix rows...`);
        await pollConflicts(result.job_id);
      }
      await fetchConflicts();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGeneratingConflicts(false);
    }
  }

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

  return (
    <div className="min-h-screen bg-canvas">
      <div className="px-4 sm:px-6 py-6">
        <div className="flex flex-col gap-6">
          <div className="flex items-end justify-between">
            <div>
              <h1 className="font-display text-[32px] font-bold leading-[1.0] text-ink" style={{ letterSpacing: "-1px" }}>
                Research Gaps & Conflicts
              </h1>
              <p className="mt-2 text-sm text-charcoal">
                Identify evidence-based research gaps and conflicting findings from your literature matrix.
              </p>
            </div>
          </div>

          <ProjectSelector projects={projects} selectedId={selectedProjectId} onChange={setSelectedProjectId} />

          <div className="flex gap-1 rounded-[10px] bg-surface-bone p-1 w-fit">
            <button
              onClick={() => setActiveTab("gaps")}
              className={`font-ui flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold transition-colors ${
                activeTab === "gaps" ? "bg-surface-card text-ink shadow-sm" : "text-charcoal hover:text-ink"
              }`}
            >
              <Lightbulb size={16} />Gaps ({gaps.length})
            </button>
            <button
              onClick={() => setActiveTab("conflicts")}
              className={`font-ui flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold transition-colors ${
                activeTab === "conflicts" ? "bg-surface-card text-ink shadow-sm" : "text-charcoal hover:text-ink"
              }`}
            >
              <Warning size={16} />Conflicts ({conflicts.length})
            </button>
          </div>

          {activeTab === "gaps" && (
            <GapsTab
              gaps={gaps}
              loading={loadingGaps}
              generating={generatingGaps}
              expandedId={expandedGapId}
              onToggleExpand={(id) => setExpandedGapId(expandedGapId === id ? null : id)}
              onGenerate={handleGenerateGaps}
              onDelete={handleDeleteGap}
            />
          )}

          {activeTab === "conflicts" && (
            <ConflictsTab
              conflicts={conflicts}
              loading={loadingConflicts}
              generating={generatingConflicts}
              expandedId={expandedConflictId}
              onToggleExpand={(id) => setExpandedConflictId(expandedConflictId === id ? null : id)}
              onGenerate={handleGenerateConflicts}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function GapsTab({ gaps, loading, generating, expandedId, onToggleExpand, onGenerate, onDelete }: {
  gaps: GapResponse[];
  loading: boolean;
  generating: boolean;
  expandedId: string | null;
  onToggleExpand: (id: string) => void;
  onGenerate: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <>
      <div className="flex items-center gap-3">
        <button
          onClick={onGenerate}
          disabled={generating}
          className="focus-ring font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
        >
          {generating ? (
            <><span className="h-4 w-4 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />Generating…</>
          ) : (
            <><Lightbulb size={16} />Generate Gaps</>
          )}
        </button>
        {gaps.length > 0 && (
          <button
            onClick={onGenerate}
            disabled={generating}
            className="font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary/10 px-5 text-sm font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
          >
            <ArrowCounterClockwise size={16} />Regenerate
          </button>
        )}
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-[10px] bg-surface-card p-5 animate-pulse" style={{ border: "1px solid var(--hairline)" }}>
              <div className="h-4 w-3/4 rounded bg-surface-bone" />
              <div className="mt-2 h-3 w-full rounded bg-surface-bone" />
              <div className="mt-2 h-3 w-5/6 rounded bg-surface-bone" />
            </div>
          ))}
        </div>
      ) : gaps.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center rounded-[12px] bg-surface-card" style={{ border: "1px solid var(--hairline)" }}>
          <Lightbulb size={40} className="text-stone mb-4" />
          <p className="font-ui text-base font-semibold text-ink">No research gaps yet</p>
          <p className="mt-2 text-sm text-charcoal max-w-md">Generate a literature matrix first, then use this tool to identify evidence-based research gaps.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {gaps.map((gap) => (
            <GapCard
              key={gap.id}
              gap={gap}
              expanded={expandedId === gap.id}
              onToggle={() => onToggleExpand(gap.id)}
              onDelete={() => onDelete(gap.id)}
              confidenceColor={confidenceColor}
            />
          ))}
        </div>
      )}
    </>
  );
}

function ConflictsTab({ conflicts, loading, generating, expandedId, onToggleExpand, onGenerate }: {
  conflicts: ConflictResponse[];
  loading: boolean;
  generating: boolean;
  expandedId: string | null;
  onToggleExpand: (id: string) => void;
  onGenerate: () => void;
}) {
  return (
    <>
      <div className="flex items-center gap-3">
        <button
          onClick={onGenerate}
          disabled={generating}
          className="focus-ring font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
        >
          {generating ? (
            <><span className="h-4 w-4 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />Detecting…</>
          ) : (
            <><Warning size={16} />Detect Conflicts</>
          )}
        </button>
        {conflicts.length > 0 && (
          <button
            onClick={onGenerate}
            disabled={generating}
            className="font-ui inline-flex items-center gap-2 h-[44px] rounded-full bg-primary/10 px-5 text-sm font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
          >
            <ArrowCounterClockwise size={16} />Redetect
          </button>
        )}
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div key={i} className="rounded-[10px] bg-surface-card p-5 animate-pulse" style={{ border: "1px solid var(--hairline)" }}>
              <div className="h-4 w-3/4 rounded bg-surface-bone" />
              <div className="mt-2 h-3 w-full rounded bg-surface-bone" />
            </div>
          ))}
        </div>
      ) : conflicts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center rounded-[12px] bg-surface-card" style={{ border: "1px solid var(--hairline)" }}>
          <Warning size={40} className="text-stone mb-4" />
          <p className="font-ui text-base font-semibold text-ink">No conflicts detected</p>
          <p className="mt-2 text-sm text-charcoal max-w-md">Conflicting findings are detected by comparing matrix rows that share the same method or dataset but report opposing results.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {conflicts.map((conflict) => (
            <ConflictCard
              key={conflict.id}
              conflict={conflict}
              expanded={expandedId === conflict.id}
              onToggle={() => onToggleExpand(conflict.id)}
              confidenceColor={confidenceColor}
            />
          ))}
        </div>
      )}
    </>
  );
}
