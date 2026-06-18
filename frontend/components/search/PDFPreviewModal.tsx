"use client";

import { useEffect, useRef, useState } from "react";
import { X, ArrowSquareOut, DownloadSimple, Spinner, FilePdf } from "@phosphor-icons/react";
import type { PaperResult } from "@/lib/types";
import { MathText } from "./MathText";

/**
 * Full-featured PDF preview modal.
 *
 * - Inline preview via an <iframe> (Chrome / Edge / Firefox all render PDFs
 *   natively — no extra dependency required).
 * - Header shows paper title, authors, year/venue for context.
 * - "Open in new tab" + "Download" actions as a fallback (some browsers
 *   refuse to render PDFs inline for security reasons — e.g. when the
 *   response has Content-Disposition: attachment).
 * - Closes on ESC or backdrop click.
 */
export function PDFPreviewModal({
  paper,
  pdfUrl,
  isOpen,
  onClose,
}: {
  paper: PaperResult;
  pdfUrl: string;
  isOpen: boolean;
  onClose: () => void;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  // Reset loading state every time we open or switch to a different paper
  useEffect(() => {
    if (isOpen) {
      setLoaded(false);
      setFailed(false);
    }
  }, [isOpen, pdfUrl]);

  // Lock body scroll while open + close on ESC
  useEffect(() => {
    if (!isOpen) return;
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
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const authorsLine = paper.authors
    ? paper.authors
        .slice(0, 3)
        .map((a) => a.name)
        .join(", ") + (paper.authors.length > 3 ? " et al." : "")
    : null;

  // Filename used by the "Download" button — prefer the basename of pdf_path
  // (e.g. "2301.12345.pdf") so the user gets a sensible name.
  const downloadName = (() => {
    if (paper.pdf_path) {
      const parts = paper.pdf_path.split("/").filter(Boolean);
      const last = parts[parts.length - 1];
      if (last) return last;
    }
    const slug = paper.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60);
    return `${slug || "paper"}.pdf`;
  })();

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-label={`PDF preview: ${paper.title}`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-fade-in p-4 sm:p-8"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div
        className="flex h-full max-h-[920px] w-full max-w-[1100px] flex-col overflow-hidden rounded-[16px] bg-surface-card shadow-2xl animate-scale-in"
        style={{ border: "1px solid var(--hairline)" }}
      >
        {/* Header */}
        <div
          className="flex shrink-0 items-start gap-4 px-6 py-4"
          style={{ borderBottom: "1px solid var(--hairline)" }}
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-violet-50 text-violet-600">
            <FilePdf size={18} weight="fill" />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              className="font-ui line-clamp-2 text-[15px] font-semibold leading-[1.4] text-ink"
              title={paper.title}
            >
              <MathText text={paper.title} />
            </h2>
            <p className="mt-0.5 line-clamp-1 text-[12px] text-ash">
              {authorsLine}
              {authorsLine && paper.year ? " · " : ""}
              {paper.year}
              {paper.venue ? ` · ${paper.venue}` : ""}
            </p>
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
              <p className="max-w-md text-[12px] text-white/60">
                Your browser refused to render the PDF. Use the download or
                "open in new tab" buttons above.
              </p>
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
            ref={iframeRef}
            key={pdfUrl}
            src={`${pdfUrl}#toolbar=1&navpanes=0&scrollbar=1`}
            title={paper.title}
            className="h-full w-full"
            onLoad={() => setLoaded(true)}
            onError={() => setFailed(true)}
          />
        </div>

        {/* Footer */}
        <div
          className="flex shrink-0 items-center justify-between gap-3 px-6 py-3 text-[12px] text-ash"
          style={{ borderTop: "1px solid var(--hairline)" }}
        >
          <span className="truncate font-ui">
            {paper.pdf_source ? `Source: ${paper.pdf_source}` : "PDF preview"}
          </span>
          <span className="font-ui shrink-0">Press Esc to close</span>
        </div>
      </div>
    </div>
  );
}
