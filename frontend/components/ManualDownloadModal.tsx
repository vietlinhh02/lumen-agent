"use client";

import { useEffect, useState, useRef, type FormEvent } from "react";
import { toast } from "sonner";
import { X } from "@phosphor-icons/react";

export function ManualDownloadModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (url: string) => void;
}) {
  const [url, setUrl] = useState("");
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (url.trim().startsWith("http")) {
      onSubmit(url.trim());
    } else {
      toast.error("Please enter a valid URL starting with http/https");
    }
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm animate-fade-in"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div
        className="w-full max-w-[500px] rounded-[16px] bg-surface-card p-8 shadow-xl animate-scale-in"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-[22px] font-bold leading-[1.2] text-ink"
            style={{ letterSpacing: "-0.5px" }}>
            Provide Direct PDF URL
          </h2>
          <button
            onClick={onClose}
            className="flex h-[32px] w-[32px] items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
          >
            <X size={16} weight="bold" />
          </button>
        </div>
        <p className="mb-5 text-sm leading-[1.6] text-charcoal">
          Auto-download failed (no open access or API rate limited). 
          If you have a link (like from ResearchGate or Google Scholar), paste the direct PDF URL below to download it:
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="url"
              placeholder="https://example.com/paper.pdf"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
              className="focus-ring h-[48px] w-full rounded-full bg-surface-card px-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
              style={{ border: "1px solid var(--hairline)" }}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="font-ui h-[44px] flex-1 rounded-full bg-surface-bone text-sm font-semibold text-charcoal hover:text-ink transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="font-ui h-[44px] flex-1 rounded-full bg-primary text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep"
            >
              Download PDF
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
