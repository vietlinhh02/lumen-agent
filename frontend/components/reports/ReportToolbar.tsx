"use client";

import { useRef, useState, useEffect } from "react";
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  MagnifyingGlass,
  Download,
  List,
} from "@phosphor-icons/react";
import type { TocEntry } from "@/lib/markdown";

interface Props {
  validationStatus: string;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  toc: TocEntry[];
  activeSection: string | null;
  onScrollToSection: (id: string) => void;
  onBack: () => void;
  onExport: () => void;
}

export function ReportToolbar({
  validationStatus,
  searchQuery,
  onSearchChange,
  toc,
  activeSection,
  onScrollToSection,
  onBack,
  onExport,
}: Props) {
  const [showMobileSearch, setShowMobileSearch] = useState(false);

  return (
    <>
      <div
        className="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5 bg-surface-card shrink-0"
        style={{ borderBottom: "1px solid var(--hairline)" }}
      >
        <button
          onClick={onBack}
          className="flex items-center gap-1 font-ui text-[12px] text-charcoal hover:text-ink transition-colors shrink-0"
        >
          <ArrowLeft size={14} />
        </button>
        <div className="h-4 w-px bg-[var(--hairline)] shrink-0" />
        <span
          className={`shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
            validationStatus === "valid"
              ? "bg-green-50 text-green-700"
              : "bg-red-50 text-red-700"
          }`}
        >
          {validationStatus === "valid" ? (
            <CheckCircle size={10} />
          ) : (
            <XCircle size={10} />
          )}
          {validationStatus === "valid" ? "Valid" : "Invalid"}
        </span>

        <div className="hidden sm:flex flex-1 min-w-[100px] max-w-xs relative">
          <MagnifyingGlass
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-ash"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search in review…"
            className="focus-ring h-[30px] w-full rounded-full bg-surface-bone pl-8 pr-3 font-ui text-[12px] text-ink outline-none"
            style={{ border: "1px solid var(--hairline)" }}
          />
        </div>
        <button
          onClick={() => setShowMobileSearch((v) => !v)}
          className="sm:hidden flex items-center justify-center h-[30px] w-[30px] rounded-full bg-surface-bone text-charcoal hover:text-ink transition-colors"
          style={{ border: "1px solid var(--hairline)" }}
        >
          <MagnifyingGlass size={14} />
        </button>

        {toc.length > 0 && (
          <TocDropdown toc={toc} activeId={activeSection} onSelect={onScrollToSection} />
        )}

        <div className="flex-1" />

        <button
          onClick={onExport}
          className="flex items-center gap-1.5 h-[28px] rounded-full bg-primary px-2.5 sm:px-3 font-ui text-[11px] font-semibold text-on-primary hover:bg-primary-deep transition-colors shrink-0"
        >
          <Download size={12} />
          <span className="hidden sm:inline">Export</span>
        </button>
      </div>

      <div
        className={`sm:hidden overflow-hidden transition-all duration-200 ease-out ${
          showMobileSearch ? "max-h-[60px] opacity-100" : "max-h-0 opacity-0"
        }`}
      >
        <div className="px-3 py-2 bg-surface-card" style={{ borderBottom: "1px solid var(--hairline)" }}>
          <div className="relative">
            <MagnifyingGlass
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-ash"
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search in review…"
              autoFocus={showMobileSearch}
              className="focus-ring h-[32px] w-full rounded-full bg-surface-bone pl-8 pr-3 font-ui text-[13px] text-ink outline-none"
              style={{ border: "1px solid var(--hairline)" }}
            />
          </div>
        </div>
      </div>
    </>
  );
}

function TocDropdown({
  toc,
  activeId,
  onSelect,
}: {
  toc: TocEntry[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 h-[30px] rounded-full bg-surface-bone px-2.5 sm:px-3 font-ui text-[11px] text-charcoal hover:text-ink transition-colors"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <List size={12} />
        <span className="hidden sm:inline">Sections</span>
      </button>
      {open && (
        <div
          className="absolute left-0 top-[36px] z-50 w-[220px] rounded-[10px] bg-surface-card p-1 shadow-lg max-h-[300px] overflow-y-auto scrollbar-hide"
          style={{ border: "1px solid var(--hairline)" }}
        >
          {toc.map((entry) => (
            <button
              key={entry.id}
              onClick={() => {
                onSelect(entry.id);
                setOpen(false);
              }}
              className={`block w-full text-left font-ui text-[12px] px-3 py-2 rounded-[6px] transition-colors ${
                entry.level === 3 ? "pl-6" : ""
              } ${
                activeId === entry.id
                  ? "bg-primary/10 text-primary font-semibold"
                  : "text-ink hover:bg-surface-bone"
              }`}
            >
              {entry.text}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
