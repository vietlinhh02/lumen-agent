"use client";

import { Play, Spinner, Table } from "@phosphor-icons/react";

interface Props {
  projectSelected: boolean;
  generating: boolean;
  progress?: {
    processed: number;
    total: number;
    current: string;
  } | null;
  onGenerate: () => void;
}

export function MatrixHeader({ projectSelected, generating, progress, onGenerate }: Props) {
  const percent =
    progress && progress.total > 0
      ? Math.min(100, Math.round((progress.processed / progress.total) * 100))
      : 0;

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="flex-1">
        <h1
          className="font-display text-[36px] font-bold leading-[1.0] text-ink"
          style={{ letterSpacing: "-1px" }}
        >
          Literature Matrix
        </h1>
        <p className="mt-2 max-w-lg text-base leading-[1.6] text-charcoal">
          Structured evidence extracted from saved papers. Click any cell to
          edit — changes are saved instantly.
        </p>
        {generating && progress ? (
          <div className="mt-4 max-w-xl rounded-2xl border border-line bg-white/80 p-4">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-ui font-semibold text-ink">
                Processing {progress.processed}/{progress.total} papers
              </span>
              <span className="font-ui text-charcoal">{percent}%</span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${percent}%` }}
              />
            </div>
            <p className="mt-3 truncate font-ui text-sm text-charcoal">
              {progress.current ? `Current: ${progress.current}` : "Preparing papers..."}
            </p>
          </div>
        ) : null}
      </div>

      {projectSelected && (
        <button
          onClick={onGenerate}
          disabled={generating}
          className="focus-ring font-ui inline-flex h-[44px] items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-all hover:bg-primary-deep active:scale-95 disabled:opacity-50"
        >
          {generating ? (
            <Spinner size={16} className="animate-spin" />
          ) : (
            <Play size={16} weight="fill" />
          )}
          {generating ? "Generating…" : "Generate Matrix"}
        </button>
      )}
    </div>
  );
}
