"use client";

import { useState } from "react";
import {
  User,
  Calendar,
  Buildings,
  Quotes,
  BookmarkSimple,
  CheckCircle,
  DownloadSimple,
  Spinner,
  Eye,
  XCircle,
} from "@phosphor-icons/react";
import type { PaperResult } from "@/lib/types";
import { MathText } from "./MathText";

const EXCLUSION_REASONS = [
  { value: "wrong_population", label: "Wrong population" },
  { value: "wrong_intervention_or_topic", label: "Wrong topic" },
  { value: "wrong_outcome", label: "Wrong outcome" },
  { value: "wrong_study_type", label: "Wrong study type" },
  { value: "not_peer_reviewed", label: "Not peer reviewed" },
  { value: "outside_date_range", label: "Outside date range" },
  { value: "duplicate", label: "Duplicate" },
  { value: "no_full_text", label: "No full text" },
  { value: "insufficient_relevance", label: "Insufficient relevance" },
  { value: "other", label: "Other" },
];

function formatAuthors(authors: Array<{ name: string; author_id?: string | null }>) {
  if (!authors || authors.length === 0) return null;
  const names = authors.map((a) => a.name);
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 3).join(", ")} et al.`;
}

function scoreBadgeClass(score: string) {
  return { high: "bg-green-50 text-green-700", medium: "bg-amber-50 text-amber-700", low: "bg-ash/10 text-ash" }[score] || "";
}

function hasSourceValue(sourceSpecific: Record<string, unknown>, key: string) {
  const value = sourceSpecific[key];
  return typeof value === "string" ? value.length > 0 : Boolean(value);
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
  onReject,
  onUnsave,
  onDownload,
  onPreview,
  saving,
  savingPdf,
  saved,
  rejected,
  score,
}: {
  paper: PaperResult;
  projectId: string | null;
  onSave: (paper: PaperResult) => void;
  onReject?: (paper: PaperResult, exclusionReason: string) => void;
  onUnsave: (paper: PaperResult) => void;
  /** Trigger a lazy PDF download for this paper. */
  onDownload?: (paper: PaperResult) => void;
  /** Open the inline PDF preview modal for an already-downloaded paper. */
  onPreview?: (paper: PaperResult) => void;
  saving: boolean;
  savingPdf?: boolean;
  saved: boolean;
  rejected?: boolean;
  score?: string;
}) {
  const authorsStr = formatAuthors(paper.authors);
  const isDownloaded = paper.pdf_downloaded;
  // `can_download` is a static metadata hint from the backend; fall back to
  // checking the same conditions on the client for older sessions.
  const canDownload = paper.can_download ?? Boolean(
    paper.arxiv_id || hasSourceValue(paper.source_specific, "pdf_url"),
  );
  const pdfHref = paper.pdf_path || null;

  const [showLowRelevanceModal, setShowLowRelevanceModal] = useState(false);
  const [exclusionReason, setExclusionReason] = useState("insufficient_relevance");

  const handleSaveClick = () => {
    if (score === "low") {
      setShowLowRelevanceModal(true);
    } else {
      onSave(paper);
    }
  };

  const handleConfirmSave = () => {
    setShowLowRelevanceModal(false);
    onSave(paper);
  };

  const handleCancelSave = () => {
    setShowLowRelevanceModal(false);
  };

  const handleReject = () => {
    if (!onReject) return;
    setShowLowRelevanceModal(false);
    onReject(paper, exclusionReason);
  };

  return (
    <div
      className={`rounded-[12px] bg-surface-card p-5 transition-all duration-200 ${
        isDownloaded ? "ring-1 ring-emerald-300/60" : ""
      }`}
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            <h3 className="font-ui text-[15px] font-semibold leading-[1.4] text-ink">
              <MathText text={paper.title} />
            </h3>
          </div>
          {isDownloaded && (
            <p className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
              <CheckCircle size={12} weight="fill" />
              PDF ready to read
            </p>
          )}
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
      {paper.abstract && <p className="mt-2.5 text-[13px] leading-[1.6] text-body line-clamp-3"><MathText text={paper.abstract} /></p>}
      <div className="mt-3 flex items-center justify-between gap-2 flex-wrap">
        <SourceBadges paper={paper} />
        <div className="flex items-center gap-2">
          {/* Lazy PDF download — only shown when the paper is known to be
              downloadable (arxiv_id or open-access PDF URL) AND not yet
              downloaded this session. */}
          {!isDownloaded && canDownload && onDownload && (
            <button
              onClick={() => onDownload(paper)}
              disabled={savingPdf}
              title="Download PDF (lazy)"
              className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-surface-bone px-4 text-[13px] font-medium text-charcoal transition-all duration-200 hover:bg-ash/15 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {savingPdf ? (
                <Spinner size={14} className="animate-spin" weight="bold" />
              ) : (
                <DownloadSimple size={14} weight="bold" />
              )}
              {savingPdf ? "Downloading…" : "PDF"}
            </button>
          )}
          {isDownloaded && pdfHref && (
            onPreview ? (
              <button
                onClick={() => onPreview(paper)}
                title="Preview PDF"
                className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-violet-50 px-4 text-[13px] font-semibold text-violet-700 transition-all duration-200 hover:bg-violet-100 active:scale-95"
              >
                <Eye size={14} weight="bold" />
                View
              </button>
            ) : (
              <a
                href={pdfHref}
                target="_blank"
                rel="noopener noreferrer"
                title="Open PDF"
                className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-violet-50 px-4 text-[13px] font-semibold text-violet-700 transition-all duration-200 hover:bg-violet-100 active:scale-95"
              >
                <Eye size={14} weight="bold" />
                View
              </a>
            )
          )}
          {rejected ? (
            <span className="font-ui inline-flex h-[34px] items-center gap-1.5 rounded-full bg-red-50 px-4 text-[13px] font-semibold text-red-600">
              <XCircle size={14} weight="fill" />
              Rejected
            </span>
          ) : saved ? (
            <button onClick={() => onUnsave(paper)} disabled={saving}
              className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-green-50 px-4 text-[13px] font-semibold text-green-700 transition-all duration-200 hover:bg-red-50 hover:text-red-600 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed">
              <BookmarkSimple size={14} weight="fill" />Saved
            </button>
          ) : (
            <>
              {score === "low" && onReject && (
                <button onClick={handleReject} disabled={!projectId || saving}
                  className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-surface-bone px-4 text-[13px] font-semibold text-charcoal transition-all duration-200 hover:bg-red-50 hover:text-red-600 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed">
                  <XCircle size={14} weight="bold" />
                  Reject
                </button>
              )}
              <button onClick={handleSaveClick} disabled={!projectId || saving}
                className="focus-ring font-ui inline-flex items-center gap-1.5 h-[34px] rounded-full bg-primary px-4 text-[13px] font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed">
                <BookmarkSimple size={14} weight="bold" />
                Save
              </button>
            </>
          )}
        </div>
      </div>

      {showLowRelevanceModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
          <div className="w-[400px] max-w-[90vw] rounded-[16px] bg-surface-card p-6 shadow-xl animate-scale-in" style={{ border: "1px solid var(--hairline)" }}>
            <h3 className="font-display text-[20px] font-bold text-ink mb-2">Low Relevance Warning</h3>
            <p className="text-sm text-charcoal mb-6 leading-relaxed">
              AI has evaluated this paper as having <strong className="text-ink">low relevance</strong> to your project topic. Saving irrelevant papers may degrade the quality of your Literature Review. Are you sure you want to save it?
            </p>
            {onReject && (
              <label className="mb-5 block">
                <span className="mb-1.5 block font-ui text-[12px] font-semibold text-ink">
                  Exclusion reason
                </span>
                <select
                  value={exclusionReason}
                  onChange={(event) => setExclusionReason(event.target.value)}
                  className="focus-ring h-[40px] w-full rounded-full bg-surface-card px-4 font-ui text-[13px] text-ink"
                  style={{ border: "1px solid var(--hairline)" }}
                >
                  {EXCLUSION_REASONS.map((reason) => (
                    <option key={reason.value} value={reason.value}>
                      {reason.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={handleCancelSave}
                className="focus-ring h-[36px] rounded-full px-5 font-ui text-[13px] font-medium text-charcoal hover:bg-surface-bone transition-colors"
              >
                Cancel
              </button>
              {onReject && (
                <button
                  onClick={handleReject}
                  className="focus-ring h-[36px] rounded-full bg-surface-bone px-5 font-ui text-[13px] font-semibold text-charcoal hover:bg-red-50 hover:text-red-600 transition-colors"
                >
                  Reject
                </button>
              )}
              <button
                onClick={handleConfirmSave}
                className="focus-ring h-[36px] rounded-full bg-red-50 text-red-600 px-5 font-ui text-[13px] font-semibold hover:bg-red-100 transition-colors"
              >
                Save anyway
              </button>
            </div>
          </div>
        </div>
      )}
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
