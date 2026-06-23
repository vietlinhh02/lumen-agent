"use client";

import { Check, Spinner, X } from "@phosphor-icons/react";
import type { AutoSearchProgressJson } from "@/lib/types";

interface Props {
  progress: AutoSearchProgressJson | null;
  isDone: boolean;
  isFailed: boolean;
  errorMessage?: string | null;
}

const PHASES = [
  { key: "searching", label: "Searching 4 sources" },
  { key: "scoring", label: "LLM scoring candidates" },
  { key: "filtering", label: "Picking top N" },
  { key: "saving", label: "Auto-saving" },
] as const;

function phaseIndex(phase: string | undefined): number {
  if (phase === "searching" || phase === "queued") return 0;
  if (phase === "scoring") return 1;
  if (phase === "filtering") return 2;
  if (phase === "saving") return 3;
  if (phase === "done") return 4;
  return 0;
}

function _phaseSubtext(p: AutoSearchProgressJson): string {
  if (p.phase === "searching") {
    // Multi-query fan-out: show "queries k/N" + total papers found so far
    // (deduped across queries).
    const qPart =
      p.queries_done !== undefined && p.queries_total !== undefined
        ? `${p.queries_done}/${p.queries_total} queries · `
        : "";
    const papersPart =
      p.papers_found !== undefined ? `${p.papers_found} unique papers` : "Starting…";
    const multiMatch =
      p.multi_match_papers !== undefined && p.multi_match_papers > 0
        ? ` (${p.multi_match_papers} matched 2+ queries)`
        : "";
    return `${qPart}${papersPart}${multiMatch}`;
  }
  if (p.phase === "scoring") {
    if (p.papers_scored !== undefined && p.papers_total !== undefined) {
      return `${p.papers_scored}/${p.papers_total} scored`;
    }
    return "Starting…";
  }
  if (p.phase === "filtering") {
    if (p.kept !== undefined) return `keeping top ${p.kept}`;
    return "Starting…";
  }
  if (p.phase === "saving") {
    if (p.saved !== undefined && p.total !== undefined) {
      return `${p.saved}/${p.total} saved`;
    }
    return "Starting…";
  }
  return "";
}

export function AutoSearchProgress({
  progress,
  isDone,
  isFailed,
  errorMessage,
}: Props) {
  const currentIdx = phaseIndex(progress?.phase);
  const percent = progress?.percent ?? 0;

  return (
    <div className="font-ui rounded-xl border border-hairline bg-surface-card p-4 space-y-3">
      {/* Progress bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-2 rounded-full bg-surface-bone overflow-hidden">
          <div
            className="h-full bg-primary transition-all duration-500"
            style={{ width: `${isFailed ? 0 : percent}%` }}
          />
        </div>
        <span className="text-[12px] font-semibold text-ink tabular-nums">
          {isFailed ? "Failed" : `${percent}%`}
        </span>
      </div>

      {/* Phase list */}
      <ol className="space-y-1.5">
        {PHASES.map((p, i) => {
          const isPast = currentIdx > i || isDone;
          const isCurrent = currentIdx === i && !isDone && !isFailed;
          const isPending = currentIdx < i;
          return (
            <li
              key={p.key}
              className={`flex items-center gap-2 text-[12px] ${
                isCurrent
                  ? "text-ink font-semibold"
                  : isPast
                    ? "text-green-700"
                    : "text-ash"
              }`}
            >
              {isPast ? (
                <Check size={12} weight="bold" />
              ) : isCurrent ? (
                <Spinner size={12} className="animate-spin" />
              ) : (
                <span className="w-3 h-3 rounded-full border border-hairline" />
              )}
              <span>{p.label}</span>
              {isCurrent && progress && (
                <span className="ml-auto text-[11px] text-ash">
                  {_phaseSubtext(progress)}
                </span>
              )}
              {isPast && !isDone && i === currentIdx - 1 && progress && (
                <span className="ml-auto text-[11px] text-ash">
                  {_phaseSubtext(progress)}
                </span>
              )}
              {isPending ? null : null}
            </li>
          );
        })}
      </ol>

      {/* Failure message */}
      {isFailed && errorMessage && (
        <p className="text-[12px] text-red-600">
          <X size={12} className="inline mr-1" />
          {errorMessage}
        </p>
      )}

      {/* Done summary */}
      {isDone && progress && (
        <p className="text-[12px] text-green-700">
          <Check size={12} weight="bold" className="inline mr-1" />
          Auto-saved {progress.saved ?? 0} papers
          {progress.skipped ? ` (${progress.skipped} skipped)` : ""}
        </p>
      )}
    </div>
  );
}
