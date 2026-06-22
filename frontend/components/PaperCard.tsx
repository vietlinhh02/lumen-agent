import { Calendar, Buildings, Quotes, User, Trash, CircleNotch } from "@phosphor-icons/react";
import type { ProjectPaperResponse } from "@/lib/types";
import { formatAuthors } from "@/lib/utils";
import { MathText } from "./search/MathText";

const relevanceColors: Record<string, string> = {
  core: "bg-primary/10 text-primary",
  related: "bg-blue-50 text-blue-700",
  background: "bg-ash/10 text-ash",
};

const fullTextColors: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-700",
  raw_extracted: "bg-amber-50 text-amber-700",
  failed: "bg-red-50 text-red-600",
  ocr_required: "bg-ash/10 text-ash",
  pending: "bg-sky-50 text-sky-700",
  normalizing: "bg-violet-50 text-violet-700",
};

const fullTextLabels: Record<string, string> = {
  completed: "Full Text",
  raw_extracted: "Raw",
  failed: "Extract Failed",
  ocr_required: "OCR Required",
  pending: "Indexing…",
  normalizing: "Indexing…",
};

// Statuses where the user can already open the extracted text.
const viewableStatuses = new Set(["completed", "raw_extracted"]);
// Statuses that mean "still working, will auto-update".
const inProgressStatuses = new Set(["pending", "normalizing"]);

export function PaperCard({
  paper,
  onDownload,
  onRemove,
  onViewFullText,
  downloading,
  removing,
}: {
  paper: ProjectPaperResponse;
  onDownload: () => void;
  onRemove: () => void;
  onViewFullText?: () => void;
  downloading: boolean;
  removing: boolean;
}) {
  return (
    <div
      className="rounded-[10px] bg-surface-card p-5 animate-scale-in"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <h3 className="font-ui text-[14px] font-semibold leading-[1.4] text-ink">
            <MathText text={paper.title} />
          </h3>
          {paper.source_names?.includes("upload") && (
            <span
              className="font-ui shrink-0 inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700"
              title="Bài báo do người dùng tải lên"
            >
              Upload
            </span>
          )}
          {paper.full_text_status && viewableStatuses.has(paper.full_text_status) && (
            <button
              onClick={onViewFullText}
              className={`font-ui shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold transition-colors hover:opacity-80 ${
                fullTextColors[paper.full_text_status] || "bg-ash/10 text-ash"
              }`}
              title="View extracted text"
            >
              {fullTextLabels[paper.full_text_status] || paper.full_text_status}
            </button>
          )}
          {paper.full_text_status && !viewableStatuses.has(paper.full_text_status) && (
            <span
              className={`font-ui shrink-0 inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                fullTextColors[paper.full_text_status] || "bg-ash/10 text-ash"
              }`}
              title={`PDF status: ${paper.full_text_status}`}
            >
              {inProgressStatuses.has(paper.full_text_status) && (
                <CircleNotch size={10} weight="bold" className="animate-spin" />
              )}
              {fullTextLabels[paper.full_text_status] || paper.full_text_status}
            </span>
          )}
        </div>
        {paper.relevance_label && (
          <span
            className={`font-ui shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
              relevanceColors[paper.relevance_label] || relevanceColors.background
            }`}
          >
            {paper.relevance_label}
          </span>
        )}
      </div>

      {paper.abstract && (
        <p className="mt-2 text-sm leading-[1.5] text-charcoal line-clamp-3">
          <MathText text={paper.abstract} />
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ash">
          <span className="inline-flex items-center gap-1">
            <User size={12} />
            {formatAuthors(paper.authors)}
          </span>
          {paper.venue && (
            <span className="inline-flex items-center gap-1">
              <Buildings size={12} />
              {paper.venue}
            </span>
          )}
          {paper.year && (
            <span className="inline-flex items-center gap-1">
              <Calendar size={12} />
              {paper.year}
            </span>
          )}
          {paper.citation_count != null && paper.citation_count > 0 && (
            <span className="inline-flex items-center gap-1">
              <Quotes size={12} />
              {paper.citation_count}
            </span>
          )}
        </div>
        
        <div className="flex shrink-0 items-center gap-1.5">
          {paper.pdf_path ? (
            <a
              href={paper.pdf_path}
              target="_blank"
              rel="noopener noreferrer"
              className="font-ui rounded-full bg-violet-50 px-2.5 py-0.5 text-[11px] font-semibold text-violet-600 hover:bg-violet-100 transition-colors"
            >
              PDF Cached (Open)
            </a>
          ) : (
            <button
              onClick={onDownload}
              disabled={downloading || removing}
              className="font-ui rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary hover:bg-primary/20 transition-colors disabled:opacity-50"
            >
              {downloading ? "Downloading…" : "Download PDF"}
            </button>
          )}
          <button
            onClick={onRemove}
            disabled={downloading || removing}
            title="Remove paper"
            aria-label={`Remove ${paper.title}`}
            className="inline-flex h-[24px] w-[24px] items-center justify-center rounded-full bg-red-50 text-error transition-colors hover:bg-red-100 disabled:opacity-50"
          >
            <Trash size={12} weight="bold" />
          </button>
        </div>
      </div>
    </div>
  );
}
