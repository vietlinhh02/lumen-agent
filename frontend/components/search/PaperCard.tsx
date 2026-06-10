"use client";

import { User, Calendar, Buildings, Quotes, BookmarkSimple } from "@phosphor-icons/react";
import type { PaperResult } from "@/lib/types";

function formatAuthors(authors: Array<{ name: string; author_id?: string | null }>) {
  if (!authors || authors.length === 0) return null;
  const names = authors.map((a) => a.name);
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 3).join(", ")} et al.`;
}

function scoreBadgeClass(score: string) {
  return { high: "bg-green-50 text-green-700", medium: "bg-amber-50 text-amber-700", low: "bg-ash/10 text-ash" }[score] || "";
}

export function SourceBadges({ paper }: { paper: PaperResult }) {
  const badges: Array<{ label: string; className: string }> = [];
  const sourceLabels = new Set((paper.source_names || []).filter(Boolean));
  sourceLabels.forEach((source) => {
    const label = source === "semantic_scholar" ? "S2" : source.replace("_", " ");
    badges.push({ label, className: "bg-surface-bone text-charcoal" });
  });
  if (paper.arxiv_id) badges.push({ label: "arXiv", className: "bg-rose-50 text-rose-600" });
  if (paper.semantic_scholar_id && !sourceLabels.has("semantic_scholar")) {
    badges.push({ label: "S2", className: "bg-blue-50 text-blue-600" });
  }
  if (paper.is_open_access) badges.push({ label: "OA", className: "bg-emerald-50 text-emerald-600" });
  if (paper.pdf_downloaded) badges.push({ label: "PDF", className: "bg-violet-50 text-violet-600" });
  if (badges.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {badges.map((b) => (
        <span key={b.label} className={`font-ui rounded-full px-2 py-0.5 text-[10px] font-semibold ${b.className}`}>{b.label}</span>
      ))}
    </div>
  );
}

export function PaperCard({
  paper,
  projectId,
  onSave,
  onUnsave,
  saving,
  saved,
  score,
}: {
  paper: PaperResult;
  projectId: string | null;
  onSave: (paper: PaperResult) => void;
  onUnsave: (paper: PaperResult) => void;
  saving: boolean;
  saved: boolean;
  score?: string;
}) {
  const authorsStr = formatAuthors(paper.authors);
  return (
    <div className="rounded-[12px] bg-surface-card p-5 transition-all duration-200"
      style={{ border: "1px solid var(--hairline)" }}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="font-ui text-[15px] font-semibold leading-[1.4] text-ink">{paper.title}</h3>
        </div>
        <div className="flex items-center gap-1.5">
          {score && <span className={`font-ui shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${scoreBadgeClass(score)}`}>{score}</span>}
          {paper.citation_count != null && paper.citation_count > 0 && (
            <span className="font-ui shrink-0 inline-flex items-center gap-1 rounded-full bg-surface-bone px-2.5 py-1 text-[11px] font-medium text-charcoal">
              <Quotes size={11} weight="fill" />{paper.citation_count}
            </span>
          )}
        </div>
      </div>
      {authorsStr && <p className="mt-1.5 text-[13px] text-charcoal"><User size={11} className="inline align-[-2px] mr-1 text-ash" />{authorsStr}</p>}
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[12px] text-ash">
        {paper.venue && <span className="inline-flex items-center gap-1"><Buildings size={11} />{paper.venue}</span>}
        {paper.year && <span className="inline-flex items-center gap-1"><Calendar size={11} />{paper.year}</span>}
      </div>
      {paper.abstract && <p className="mt-2.5 text-[13px] leading-[1.6] text-body line-clamp-3">{paper.abstract}</p>}
      <div className="mt-3 flex items-center justify-between">
        <SourceBadges paper={paper} />
        {saved ? (
          <button onClick={() => onUnsave(paper)} disabled={saving}
            className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-green-50 px-4 text-[13px] font-semibold text-green-700 transition-all duration-200 hover:bg-red-50 hover:text-red-600 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed">
            <BookmarkSimple size={14} weight="fill" />Saved
          </button>
        ) : (
          <button onClick={() => onSave(paper)} disabled={!projectId || saving}
            className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-primary px-4 text-[13px] font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed">
            <BookmarkSimple size={14} weight="bold" />Save
          </button>
        )}
      </div>
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div className="rounded-[12px] bg-surface-card p-5 animate-pulse" style={{ border: "1px solid var(--hairline)" }}>
      <div className="h-5 w-3/4 rounded bg-surface-bone" />
      <div className="mt-2 h-4 w-1/2 rounded bg-surface-bone" />
      <div className="mt-3 h-3 w-full rounded bg-surface-bone" />
      <div className="mt-2 h-3 w-5/6 rounded bg-surface-bone" />
      <div className="mt-3 flex justify-between">
        <div className="flex gap-1.5"><div className="h-5 w-12 rounded-full bg-surface-bone" /><div className="h-5 w-10 rounded-full bg-surface-bone" /></div>
        <div className="h-[34px] w-16 rounded-full bg-surface-bone" />
      </div>
    </div>
  );
}
