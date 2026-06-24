"use client";

import { useEffect, useState } from "react";
import { X, Quotes, Spinner, Warning, Check } from "@phosphor-icons/react";
import type {
  EvidenceChunk,
  EvidenceRatingResponse,
  EvidenceRatingValue,
  EvidenceSourceKind,
} from "@/lib/types";
import { MathText } from "../search/MathText";

/** Optional rating wiring — when present, each chunk gains Accept/Weak/Wrong. */
export interface EvidenceRatingProps {
  sourceKind: EvidenceSourceKind;
  sourceId: string;
  /** Existing ratings keyed by chunk_id. */
  ratings: Record<string, EvidenceRatingResponse>;
  onRate: (args: {
    chunkId: string;
    projectPaperId: string | null;
    rating: EvidenceRatingValue;
    note: string | null;
  }) => void;
}

/**
 * T3 evidence viewer — read-only slide-over that shows the supporting
 * chunks (quote + section + page) behind a claim.
 *
 * Presentational only: each surface (matrix, gap, conflict, report) fetches
 * its own evidence and passes the result in, so the drawer stays reusable.
 */
export function EvidenceDrawer({
  open,
  onClose,
  title,
  loading,
  error,
  items,
  rating,
}: {
  open: boolean;
  onClose: () => void;
  title: string | null;
  loading: boolean;
  error: string | null;
  items: EvidenceChunk[];
  rating?: EvidenceRatingProps;
}) {
  // Close on ESC while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Supporting evidence"
      className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-sm animate-fade-in"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="flex h-full w-full max-w-[460px] flex-col bg-surface-card shadow-2xl animate-slide-in-right"
        style={{ borderLeft: "1px solid var(--hairline)" }}
      >
        {/* Header */}
        <div
          className="flex shrink-0 items-start gap-3 px-5 py-4"
          style={{ borderBottom: "1px solid var(--hairline)" }}
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-violet-50 text-violet-600">
            <Quotes size={18} weight="fill" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="font-ui text-[15px] font-semibold leading-[1.3] text-ink">
              Supporting evidence
            </h2>
            {title && (
              <p className="mt-0.5 line-clamp-2 text-[12px] text-ash">
                <MathText text={title} />
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            title="Close (Esc)"
            className="focus-ring flex h-[32px] w-[32px] shrink-0 items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
          >
            <X size={16} weight="bold" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-ash">
              <Spinner size={24} className="animate-spin" weight="bold" />
              <p className="font-ui text-[13px]">Finding supporting quotes…</p>
            </div>
          )}

          {!loading && error && (
            <div className="flex flex-col items-center justify-center gap-2 py-16 px-4 text-center text-ash">
              <Warning size={28} weight="duotone" />
              <p className="font-ui text-[13px] font-semibold text-ink">
                Couldn&apos;t load evidence
              </p>
              <p className="font-ui text-[12px]">{error}</p>
            </div>
          )}

          {!loading && !error && items.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-2 py-16 px-4 text-center text-ash">
              <Quotes size={28} weight="duotone" />
              <p className="font-ui text-[13px] font-semibold text-ink">
                No supporting chunks found
              </p>
              <p className="font-ui text-[12px]">
                This paper has no indexed full-text chunks for this claim yet.
              </p>
            </div>
          )}

          {!loading && !error && items.length > 0 && (
            <ul className="flex flex-col gap-3">
              {items.map((item) => (
                <li
                  key={item.chunk_id}
                  className="rounded-[12px] bg-surface-bone/40 p-3.5"
                  style={{ border: "1px solid var(--hairline)" }}
                >
                  <div className="mb-2 flex flex-wrap items-center gap-1.5">
                    {item.content_type && (
                      <span className="font-ui inline-flex items-center rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-600">
                        {item.content_type}
                      </span>
                    )}
                    {item.section_label && (
                      <span className="font-ui text-[11px] font-medium text-ash">
                        {item.section_label}
                      </span>
                    )}
                    {item.page_start != null && (
                      <span className="font-ui text-[11px] text-stone">
                        p.{item.page_start}
                        {item.page_end != null && item.page_end !== item.page_start
                          ? `–${item.page_end}`
                          : ""}
                      </span>
                    )}
                  </div>
                  <blockquote className="font-ui text-[13px] leading-[1.6] text-body">
                    <MathText text={item.chunk_text} />
                  </blockquote>
                  {rating && (
                    <RatingControls
                      // Remount when the saved rating changes so the note
                      // field re-syncs without a setState-in-effect.
                      key={`${item.chunk_id}:${rating.ratings[item.chunk_id]?.updated_at ?? ""}`}
                      chunkId={item.chunk_id}
                      projectPaperId={item.project_paper_id}
                      current={rating.ratings[item.chunk_id]}
                      onRate={rating.onRate}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex shrink-0 items-center justify-between gap-3 px-5 py-3 text-[11px] text-ash"
          style={{ borderTop: "1px solid var(--hairline)" }}
        >
          <span className="font-ui">
            {items.length > 0
              ? `${items.length} quote${items.length === 1 ? "" : "s"}`
              : "Evidence"}
          </span>
          <span className="font-ui">Press Esc to close</span>
        </div>
      </div>
    </div>
  );
}

const RATING_BUTTONS: {
  value: EvidenceRatingValue;
  label: string;
  Icon: typeof Check;
  active: string;
}[] = [
  { value: "accepted", label: "Accept", Icon: Check, active: "bg-green-50 text-green-700 ring-1 ring-green-200" },
  { value: "weak", label: "Weak", Icon: Warning, active: "bg-amber-50 text-amber-700 ring-1 ring-amber-200" },
  { value: "wrong", label: "Wrong", Icon: X, active: "bg-red-50 text-red-700 ring-1 ring-red-200" },
];

/**
 * Per-chunk rating row: "Is this *quote* relevant evidence for the *claim*?"
 * A weak/wrong mark reveals an optional note ("Why was this rated weak?").
 */
function RatingControls({
  chunkId,
  projectPaperId,
  current,
  onRate,
}: {
  chunkId: string;
  projectPaperId: string | null;
  current: EvidenceRatingResponse | undefined;
  onRate: EvidenceRatingProps["onRate"];
}) {
  const value = current?.rating ?? null;
  const [note, setNote] = useState(current?.note ?? "");

  const showNote = value === "weak" || value === "wrong";

  function choose(next: EvidenceRatingValue) {
    onRate({
      chunkId,
      projectPaperId,
      rating: next,
      // Accept clears any prior "why weak" note; weak/wrong keep it.
      note: next === "accepted" ? null : note.trim() || null,
    });
  }

  function saveNote() {
    if (!showNote || !value) return;
    if ((current?.note ?? "") === (note.trim() || null)) return;
    onRate({ chunkId, projectPaperId, rating: value, note: note.trim() || null });
  }

  return (
    <div className="mt-3 border-t border-[var(--hairline)] pt-2.5">
      <div className="flex items-center gap-1.5">
        <span className="font-ui mr-1 text-[10px] font-semibold uppercase tracking-wide text-stone">
          Relevant?
        </span>
        {RATING_BUTTONS.map(({ value: v, label, Icon, active }) => (
          <button
            key={v}
            onClick={() => choose(v)}
            className={`focus-ring font-ui inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
              value === v ? active : "text-charcoal hover:bg-surface-bone"
            }`}
          >
            <Icon size={12} weight="bold" />
            {label}
          </button>
        ))}
      </div>
      {showNote && (
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={saveNote}
          rows={2}
          placeholder={value === "weak" ? "Why was this rated weak?" : "Why was this rated wrong?"}
          className="focus-ring mt-2 w-full resize-none rounded-[8px] bg-surface-bone/60 px-3 py-2 font-ui text-[12px] text-body placeholder:text-stone"
          style={{ border: "1px solid var(--hairline)" }}
        />
      )}
    </div>
  );
}
