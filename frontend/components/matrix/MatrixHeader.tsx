"use client";

interface Props {
  generating: boolean;
  progress?: {
    processed: number;
    total: number;
    current: string;
  } | null;
}

export function MatrixHeader({ generating, progress }: Props) {
  const percent =
    progress && progress.total > 0
      ? Math.min(100, Math.round((progress.processed / progress.total) * 100))
      : 0;

  if (!generating || !progress) return null;

  return (
    <div className="mb-4 sm:mb-6 rounded-[12px] border border-[var(--hairline)] bg-white/80 p-3 sm:p-4">
      <div className="flex items-center justify-between gap-3 text-[12px] sm:text-sm">
        <span className="font-ui font-semibold text-ink">
          Processing {progress.processed}/{progress.total} papers
        </span>
        <span className="font-ui text-charcoal">{percent}%</span>
      </div>
      <div className="mt-2 sm:mt-3 h-1.5 sm:h-2 overflow-hidden rounded-full bg-surface-bone">
        <div
          className="h-full rounded-full bg-primary transition-all duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="mt-2 sm:mt-3 truncate font-ui text-[12px] sm:text-sm text-charcoal">
        {progress.current ? `Current: ${progress.current}` : "Preparing papers..."}
      </p>
    </div>
  );
}
