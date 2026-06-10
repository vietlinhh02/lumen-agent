"use client";

import { PencilLine, FileText, CheckCircle, XCircle, ArrowCounterClockwise } from "@phosphor-icons/react";
import type { ReportResponse } from "@/lib/types";

interface Props {
  reports: ReportResponse[];
  selectedId: string | null;
  loading: boolean;
  generating: boolean;
  onSelect: (id: string) => void;
  onGenerate: () => void;
}

export function ReportList({ reports, selectedId, loading, generating, onSelect, onGenerate }: Props) {
  return (
    <div
      className={`w-full md:w-[200px] lg:w-[240px] shrink-0 bg-surface-card flex-col transition-all duration-200 ease-out ${selectedId ? "hidden md:flex" : "flex"}`}
      style={{ borderRight: "1px solid var(--hairline)" }}
    >
      <div
        className="px-3 sm:px-4 py-3 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--hairline)" }}
      >
        <span className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide">
          Reports ({reports.length})
        </span>
        <button
          onClick={onGenerate}
          disabled={generating}
          className="focus-ring font-ui inline-flex items-center gap-1.5 h-[28px] rounded-full bg-primary px-2.5 text-[11px] font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
        >
          {generating ? (
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />
          ) : (
            <PencilLine size={11} />
          )}
          New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hide">
        {loading ? (
          <div className="p-3 space-y-2">
            {[1, 2].map((i) => (
              <div key={i} className="h-14 rounded-[8px] bg-surface-bone animate-pulse" />
            ))}
          </div>
        ) : reports.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full p-4 text-center">
            <FileText size={28} className="text-stone mb-2" />
            <p className="font-ui text-[13px] font-medium text-ink">No reports</p>
          </div>
        ) : (
          <div className="p-1.5 space-y-0.5">
            {reports.map((r) => (
              <button
                key={r.id}
                onClick={() => onSelect(r.id)}
                className={`w-full text-left rounded-[8px] px-3 py-2.5 transition-colors ${
                  selectedId === r.id ? "bg-primary/10" : "hover:bg-surface-bone"
                }`}
              >
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                    r.validation_status === "valid"
                      ? "bg-green-50 text-green-700"
                      : "bg-red-50 text-red-700"
                  }`}
                >
                  {r.validation_status === "valid" ? (
                    <CheckCircle size={9} />
                  ) : (
                    <XCircle size={9} />
                  )}
                  {r.validation_status === "valid" ? "Valid" : "Bad"}
                </span>
                <p className="font-ui text-[12px] font-medium text-ink mt-1 line-clamp-2">
                  {r.title}
                </p>
                <p className="font-ui text-[10px] text-ash mt-0.5">
                  {r.citation_audit.total_citations} citations
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      {reports.length > 0 && (
        <div className="px-3 py-2.5" style={{ borderTop: "1px solid var(--hairline)" }}>
          <button
            onClick={onGenerate}
            disabled={generating}
            className="font-ui w-full inline-flex items-center justify-center gap-1.5 h-[32px] rounded-full bg-primary/10 text-[11px] font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
          >
            <ArrowCounterClockwise size={12} />
            Regenerate
          </button>
        </div>
      )}
    </div>
  );
}
