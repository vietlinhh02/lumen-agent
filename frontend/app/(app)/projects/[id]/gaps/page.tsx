"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";
import { Lightbulb, Warning, ArrowCounterClockwise } from "@phosphor-icons/react";
import { useGapsStore } from "@/lib/stores/gaps-store";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { GapCard, ConflictCard } from "@/components/gaps";
import type { GapResponse, ConflictResponse } from "@/lib/types";

const confidenceColor = (c: string) => {
  if (c === "high") return "bg-green-50 text-green-700";
  if (c === "low") return "bg-amber-50 text-amber-700";
  return "bg-blue-50 text-blue-700";
};

export default function ProjectGapsPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ?? "";

  const setSelectedProjectId = useGapsStore((s) => s.setSelectedProjectId);
  const gaps = useGapsStore((s) => s.gaps);
  const conflicts = useGapsStore((s) => s.conflicts);
  const loadingGaps = useGapsStore((s) => s.loadingGaps);
  const loadingConflicts = useGapsStore((s) => s.loadingConflicts);
  const generatingGaps = useGapsStore((s) => s.generatingGaps);
  const generatingConflicts = useGapsStore((s) => s.generatingConflicts);
  const expandedGapId = useGapsStore((s) => s.expandedGapId);
  const expandedConflictId = useGapsStore((s) => s.expandedConflictId);
  const activeTab = useGapsStore((s) => s.activeTab);
  const setActiveTab = useGapsStore((s) => s.setActiveTab);
  const toggleGapExpand = useGapsStore((s) => s.toggleGapExpand);
  const toggleConflictExpand = useGapsStore((s) => s.toggleConflictExpand);
  const fetchGaps = useGapsStore((s) => s.fetchGaps);
  const fetchConflicts = useGapsStore((s) => s.fetchConflicts);
  const generateGaps = useGapsStore((s) => s.generateGaps);
  const generateConflicts = useGapsStore((s) => s.generateConflicts);
  const deleteGap = useGapsStore((s) => s.deleteGap);

  const { poll: pollGaps } = useJobPolling({
    onSuccess: (result) => `Generated ${(result.gap_count as number) ?? 0} research gaps`,
  });
  const { poll: pollConflicts } = useJobPolling({
    onSuccess: (result) =>
      `Found ${(result.conflict_count as number) ?? 0} potential conflicts`,
  });

  useEffect(() => {
    if (projectId) setSelectedProjectId(projectId);
  }, [projectId, setSelectedProjectId]);

  useEffect(() => {
    if (!projectId) return;
    void fetchGaps(projectId);
    void fetchConflicts(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function handleGenerateGaps() {
    if (!projectId) return;
    try {
      await generateGaps(projectId, async (jobId) => {
        await pollGaps(jobId);
        return null;
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    }
  }

  async function handleGenerateConflicts() {
    if (!projectId) return;
    try {
      await generateConflicts(projectId, async (jobId) => {
        await pollConflicts(jobId);
        return null;
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generation failed");
    }
  }

  async function handleDeleteGap(gapId: string) {
    if (!projectId) return;
    const ok = await deleteGap(projectId, gapId);
    if (ok) toast.success("Gap removed");
    else toast.error("Delete failed");
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="font-display text-[22px] font-bold leading-[1.0] text-ink">
          Research Gaps & Conflicts
        </h2>
        <p className="mt-1 font-ui text-[12px] text-charcoal">
          Identify evidence-based research gaps and conflicting findings from the literature matrix.
        </p>
      </div>

      <div className="flex gap-1 rounded-[10px] bg-surface-bone p-1 w-fit mb-4">
        <button
          onClick={() => setActiveTab("gaps")}
          className={`font-ui flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold transition-colors ${
            activeTab === "gaps" ? "bg-surface-card text-ink shadow-sm" : "text-charcoal hover:text-ink"
          }`}
        >
          <Lightbulb size={15} />Gaps ({gaps.length})
        </button>
        <button
          onClick={() => setActiveTab("conflicts")}
          className={`font-ui flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold transition-colors ${
            activeTab === "conflicts" ? "bg-surface-card text-ink shadow-sm" : "text-charcoal hover:text-ink"
          }`}
        >
          <Warning size={15} />Conflicts ({conflicts.length})
        </button>
      </div>

      {activeTab === "gaps" && (
        <GapsTab
          gaps={gaps}
          loading={loadingGaps}
          generating={generatingGaps}
          expandedId={expandedGapId}
          onToggleExpand={toggleGapExpand}
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
          onToggleExpand={toggleConflictExpand}
          onGenerate={handleGenerateConflicts}
        />
      )}
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
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={onGenerate}
          disabled={generating}
          className="focus-ring font-ui inline-flex items-center gap-2 h-[40px] rounded-full bg-primary px-4 text-[13px] font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
        >
          {generating ? (
            <><span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />Generating…</>
          ) : (
            <><Lightbulb size={14} />Generate Gaps</>
          )}
        </button>
        {gaps.length > 0 && (
          <button
            onClick={onGenerate}
            disabled={generating}
            className="font-ui inline-flex items-center gap-2 h-[40px] rounded-full bg-primary/10 px-4 text-[13px] font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
          >
            <ArrowCounterClockwise size={14} />Regenerate
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
        <div className="flex flex-col items-center justify-center py-16 text-center rounded-[12px] bg-surface-card" style={{ border: "1px solid var(--hairline)" }}>
          <Lightbulb size={36} className="text-stone mb-3" weight="light" />
          <p className="font-ui text-base font-semibold text-ink">No research gaps yet</p>
          <p className="mt-2 text-sm text-charcoal max-w-md">Generate a literature matrix first, then use this tool to identify evidence-based research gaps.</p>
        </div>
      ) : (
        <div className="space-y-3">
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
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={onGenerate}
          disabled={generating}
          className="focus-ring font-ui inline-flex items-center gap-2 h-[40px] rounded-full bg-primary px-4 text-[13px] font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
        >
          {generating ? (
            <><span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />Detecting…</>
          ) : (
            <><Warning size={14} />Detect Conflicts</>
          )}
        </button>
        {conflicts.length > 0 && (
          <button
            onClick={onGenerate}
            disabled={generating}
            className="font-ui inline-flex items-center gap-2 h-[40px] rounded-full bg-primary/10 px-4 text-[13px] font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
          >
            <ArrowCounterClockwise size={14} />Redetect
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
        <div className="flex flex-col items-center justify-center py-16 text-center rounded-[12px] bg-surface-card" style={{ border: "1px solid var(--hairline)" }}>
          <Warning size={36} className="text-stone mb-3" weight="light" />
          <p className="font-ui text-base font-semibold text-ink">No conflicts detected</p>
          <p className="mt-2 text-sm text-charcoal max-w-md">Conflicting findings are detected by comparing matrix rows that share the same method or dataset but report opposing results.</p>
        </div>
      ) : (
        <div className="space-y-3">
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
