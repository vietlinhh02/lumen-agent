"use client";

import { Warning, CaretDown, CaretUp, Quotes } from "@phosphor-icons/react";
import type { ConflictResponse } from "@/lib/types";

interface Props {
  conflict: ConflictResponse;
  expanded: boolean;
  onToggle: () => void;
  onViewEvidence: (side: "a" | "b") => void;
  confidenceColor: (c: string) => string;
}

export function ConflictCard({ conflict, expanded, onToggle, onViewEvidence, confidenceColor }: Props) {
  return (
    <div
      className="rounded-[10px] bg-surface-card transition-shadow hover:shadow-md"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <button onClick={onToggle} className="flex w-full items-start gap-3 p-5 text-left">
        <div className="mt-0.5 shrink-0">
          <Warning size={20} className="text-orange-500" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-ui text-base font-semibold text-ink truncate">{conflict.title}</h3>
            <span className={`font-ui shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${confidenceColor(conflict.confidence)}`}>
              {conflict.confidence}
            </span>
          </div>
          <p className="mt-1 text-sm text-charcoal line-clamp-2">{conflict.description}</p>
        </div>
        <div className="shrink-0">
          {expanded ? <CaretUp size={16} className="text-charcoal" /> : <CaretDown size={16} className="text-charcoal" />}
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-[var(--hairline)] pt-4">
          {conflict.shared_context && (
            <div>
              <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-1">Shared Context</p>
              <p className="text-sm text-ink">{conflict.shared_context}</p>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="rounded-[8px] bg-green-50 px-4 py-3">
              <div className="flex items-start justify-between gap-2 mb-1">
                <p className="font-ui text-[12px] font-semibold text-green-700 min-w-0">{conflict.paper_a_title || "Paper A"}</p>
                <button
                  onClick={() => onViewEvidence("a")}
                  className="focus-ring font-ui inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold text-green-700 hover:bg-green-100 transition-colors"
                  title="View supporting evidence"
                >
                  <Quotes size={12} weight="bold" />
                  Evidence
                </button>
              </div>
              <p className="text-sm text-ink">{conflict.claim_a || "No claim specified"}</p>
            </div>
            <div className="rounded-[8px] bg-red-50 px-4 py-3">
              <div className="flex items-start justify-between gap-2 mb-1">
                <p className="font-ui text-[12px] font-semibold text-red-700 min-w-0">{conflict.paper_b_title || "Paper B"}</p>
                <button
                  onClick={() => onViewEvidence("b")}
                  className="focus-ring font-ui inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold text-red-700 hover:bg-red-100 transition-colors"
                  title="View supporting evidence"
                >
                  <Quotes size={12} weight="bold" />
                  Evidence
                </button>
              </div>
              <p className="text-sm text-ink">{conflict.claim_b || "No claim specified"}</p>
            </div>
          </div>
          {conflict.possible_explanation && (
            <div>
              <p className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-1">Possible Explanation</p>
              <p className="text-sm text-ink leading-relaxed">{conflict.possible_explanation}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
