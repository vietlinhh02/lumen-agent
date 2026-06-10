"use client";

import { Play, Spinner, Table } from "@phosphor-icons/react";

interface Props {
  projectSelected: boolean;
  generating: boolean;
  onGenerate: () => void;
}

export function MatrixHeader({ projectSelected, generating, onGenerate }: Props) {
  return (
    <div className="flex items-end justify-between">
      <div>
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
