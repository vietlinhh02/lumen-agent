"use client";

import { CaretLeft, CaretRight } from "@phosphor-icons/react";

interface Props {
  page: number;
  totalPages: number;
  onGoPage: (p: number) => void;
}

export function Pagination({ page, totalPages, onGoPage }: Props) {
  const pages: number[] = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  for (let i = start; i <= end; i++) pages.push(i);

  return (
    <div className="mt-6 flex items-center justify-center gap-1.5">
      <button
        onClick={() => onGoPage(page - 1)}
        disabled={page <= 1}
        className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-surface-card text-ash hover:text-ink disabled:opacity-30 transition-colors"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <CaretLeft size={14} />
      </button>
      {pages.map((p) => (
        <button
          key={p}
          onClick={() => onGoPage(p)}
          className={`font-ui h-[34px] min-w-[34px] rounded-full px-2 text-[13px] font-semibold transition-all duration-200 ${
            p === page ? "bg-ink text-on-dark" : "text-charcoal hover:bg-surface-bone hover:text-ink"
          }`}
        >
          {p}
        </button>
      ))}
      <button
        onClick={() => onGoPage(page + 1)}
        disabled={page >= totalPages}
        className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-surface-card text-ash hover:text-ink disabled:opacity-30 transition-colors"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <CaretRight size={14} />
      </button>
    </div>
  );
}
