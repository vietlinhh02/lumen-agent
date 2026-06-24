"use client";

import { useEffect, useRef, useState } from "react";
import { X, ArrowSquareOut, DownloadSimple, Spinner, FilePdf } from "@phosphor-icons/react";

/**
 * T3 Phase 4 — opens the source PDF behind a report citation in a side panel.
 *
 * Lean by design: a report reference only carries a title + served PDF URL,
 * so this takes those directly instead of the heavier search `PaperResult`
 * the search-side `PDFPreviewModal` needs. Same native <iframe> preview with
 * "open in new tab" / "download" fallbacks for browsers that refuse inline PDFs.
 */
export function CitationPdfModal({
  open,
  onClose,
  title,
  citationLabel,
  pdfUrl,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  citationLabel: string;
  pdfUrl: string;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  // Parent mounts this only while a citation is open, so a fresh mount per
  // citation starts loaded/failed at false — no setState-in-effect reset.
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  const downloadName = (() => {
    const last = pdfUrl.split("/").filter(Boolean).pop();
    return last && last.endsWith(".pdf") ? last : "paper.pdf";
  })();

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-label={`PDF: ${title}`}
      className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-sm animate-fade-in"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div
        className="flex h-full w-full max-w-[760px] flex-col bg-surface-card shadow-2xl animate-slide-in-right"
        style={{ borderLeft: "1px solid var(--hairline)" }}
      >
        {/* Header */}
        <div
          className="flex shrink-0 items-start gap-3 px-5 py-4"
          style={{ borderBottom: "1px solid var(--hairline)" }}
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-violet-50 text-violet-600">
            <FilePdf size={18} weight="fill" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-ui text-[11px] font-semibold text-primary">{citationLabel}</p>
            <h2
              className="font-ui line-clamp-2 text-[14px] font-semibold leading-[1.4] text-ink"
              title={title}
            >
              {title}
            </h2>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              title="Open in new tab"
              className="focus-ring flex h-[32px] w-[32px] items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
            >
              <ArrowSquareOut size={16} weight="bold" />
            </a>
            <a
              href={pdfUrl}
              download={downloadName}
              title="Download PDF"
              className="focus-ring flex h-[32px] w-[32px] items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
            >
              <DownloadSimple size={16} weight="bold" />
            </a>
            <button
              onClick={onClose}
              title="Close (Esc)"
              className="focus-ring flex h-[32px] w-[32px] items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
            >
              <X size={16} weight="bold" />
            </button>
          </div>
        </div>

        {/* Body — iframe PDF preview */}
        <div className="relative flex-1 bg-[#525659]">
          {!loaded && !failed && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 text-white/80">
              <Spinner size={28} className="animate-spin" weight="bold" />
              <p className="font-ui text-[13px]">Loading PDF…</p>
            </div>
          )}
          {failed && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 px-6 text-center text-white/90">
              <FilePdf size={36} weight="duotone" />
              <p className="font-ui text-[14px] font-semibold">Cannot preview this PDF inline</p>
              <div className="mt-2 flex gap-2">
                <a
                  href={pdfUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-ui inline-flex items-center gap-1.5 h-[36px] rounded-full bg-white/10 px-4 text-[13px] font-semibold text-white hover:bg-white/20 transition-colors"
                >
                  <ArrowSquareOut size={14} weight="bold" /> Open
                </a>
                <a
                  href={pdfUrl}
                  download={downloadName}
                  className="font-ui inline-flex items-center gap-1.5 h-[36px] rounded-full bg-primary px-4 text-[13px] font-semibold text-on-primary hover:bg-primary-deep transition-colors"
                >
                  <DownloadSimple size={14} weight="bold" /> Download
                </a>
              </div>
            </div>
          )}
          <iframe
            key={pdfUrl}
            src={`${pdfUrl}#toolbar=1&navpanes=0&scrollbar=1`}
            title={title}
            className="h-full w-full"
            onLoad={() => setLoaded(true)}
            onError={() => setFailed(true)}
          />
        </div>

        {/* Footer */}
        <div
          className="flex shrink-0 items-center justify-end gap-3 px-5 py-3 text-[11px] text-ash"
          style={{ borderTop: "1px solid var(--hairline)" }}
        >
          <span className="font-ui">Press Esc to close</span>
        </div>
      </div>
    </div>
  );
}
