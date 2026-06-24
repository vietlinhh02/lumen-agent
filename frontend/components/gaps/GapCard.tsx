"use client";

import { Lightbulb, CaretDown, CaretUp, Trash, Quotes } from "@phosphor-icons/react";
import type { GapResponse } from "@/lib/types";

interface Props {
  gap: GapResponse;
  expanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onViewEvidence: (projectPaperId: string) => void;
  confidenceColor: (c: string) => string;
}

export function GapCard({ gap, expanded, onToggle, onDelete, onViewEvidence, confidenceColor }: Props) {
  return (
    <div
      className="rounded-[10px] bg-surface-card transition-shadow hover:shadow-md"
      style={{ border: "1px solid var(--hairline)" }}
    >
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
            <h3 className="font-ui text-base font-semibold text-ink truncate">{gap.title}</h3>
            <span className={`font-ui shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${confidenceColor(gap.confidence)}`}>
              {gap.confidence}
            </span>
          </div>
          <p className="mt-1 text-sm text-charcoal line-clamp-2">{gap.description}</p>
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="flex h-[28px] w-[28px] items-center justify-center rounded-[6px] text-charcoal hover:text-error hover:bg-red-50 transition-colors"
            title="Delete gap"
          >
            <Trash size={14} />
          </button>
          {expanded ? <CaretUp size={16} className="text-charcoal" /> : <CaretDown size={16} className="text-charcoal" />}
        </div>
      </div>

      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-[var(--hairline)] pt-4">
          <div>
            <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-1">Suggested Research Direction</p>
            <p className="text-sm text-ink leading-relaxed">{gap.suggested_direction}</p>
          </div>
          <div>
            <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-1">Evidence Summary</p>
            <p className="text-sm text-ink leading-relaxed">{gap.evidence_summary}</p>
          </div>
          {gap.evidence.length > 0 && (
            <div>
              <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-2">Supporting Papers ({gap.evidence.length})</p>
              <div className="space-y-2">
                {gap.evidence.map((ev) => (
                  <div key={ev.project_paper_id} className="rounded-[8px] bg-surface-bone px-4 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-ui text-sm font-medium text-ink min-w-0">{ev.title || "Unknown paper"}</p>
                      <button
                        onClick={() => onViewEvidence(ev.project_paper_id)}
                        className="focus-ring font-ui inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold text-violet-600 hover:bg-violet-50 transition-colors"
                        title="View supporting evidence"
                      >
                        <Quotes size={12} weight="bold" />
                        Evidence
                      </button>
                    </div>
                    <p className="mt-1 text-[12px] text-charcoal">
                      <span className="font-semibold">{ev.evidence_type}:</span> {ev.note}
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
