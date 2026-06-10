"use client";

import { Spinner, Table, Sparkle } from "@phosphor-icons/react";

interface Props {
  loading: boolean;
  hasProject: boolean;
  hasRows: boolean;
  onGenerate: () => void;
}

export function MatrixEmptyState({ loading, hasProject, hasRows, onGenerate }: Props) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <Spinner size={28} className="animate-spin text-primary" />
        <p className="mt-3 font-ui text-sm text-ash">Loading matrix…</p>
      </div>
    );
  }

  if (!hasProject) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center animate-slide-up">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-surface-bone">
          <Table size={36} className="text-stone" weight="light" />
        </div>
        <h2
          className="font-display text-[24px] font-bold leading-[1.2] text-ink"
          style={{ letterSpacing: "-0.5px" }}
        >
          No project selected
        </h2>
        <p className="mt-3 max-w-sm text-base leading-[1.6] text-charcoal">
          Select a project above to view and edit its literature matrix.
        </p>
      </div>
    );
  }

  if (!hasRows) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center animate-slide-up">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-surface-bone">
          <Table size={36} className="text-stone" weight="light" />
        </div>
        <h2
          className="font-display text-[24px] font-bold leading-[1.2] text-ink"
          style={{ letterSpacing: "-0.5px" }}
        >
          No matrix rows yet
        </h2>
        <p className="mt-3 max-w-sm text-base leading-[1.6] text-charcoal">
          Generate a literature matrix from your saved papers to extract
          structured evidence like methods, datasets, and key results.
        </p>
        <button
          onClick={onGenerate}
          className="focus-ring font-ui mt-8 inline-flex h-[48px] items-center gap-2 rounded-full bg-primary px-6 text-base font-semibold text-on-primary transition-all hover:bg-primary-deep active:scale-95"
        >
          <Sparkle size={20} weight="fill" />
          Generate Matrix
        </button>
      </div>
    );
  }

  return null;
}
