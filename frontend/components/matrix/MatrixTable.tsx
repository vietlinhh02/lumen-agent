"use client";

import { useState } from "react";
import { CaretDown, CaretUp, Trash } from "@phosphor-icons/react";
import type { MatrixRowResponse, MatrixRowUpdate } from "@/lib/types";
import { EditableCell } from "./EditableCell";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { MathText } from "../search/MathText";

const SUMMARY_FIELDS: { key: keyof MatrixRowUpdate; label: string }[] = [
  { key: "method", label: "Method" },
  { key: "key_result", label: "Key Result" },
];

const DETAIL_FIELDS: { key: keyof MatrixRowUpdate; label: string; span?: string }[] = [
  { key: "research_problem", label: "Research Problem", span: "md:col-span-2" },
  { key: "method", label: "Method", span: "md:col-span-2" },
  { key: "dataset_or_context", label: "Dataset / Context" },
  { key: "key_result", label: "Key Result", span: "md:col-span-2" },
  { key: "limitation", label: "Limitation" },
  { key: "contribution", label: "Contribution", span: "md:col-span-2" },
  { key: "relevance", label: "Relevance", span: "md:col-span-2" },
];

interface Props {
  rows: MatrixRowResponse[];
  onEdit: (rowId: string, field: string, value: string) => void;
  onDelete: (rowId: string) => void;
}

function MatrixCard({
  row,
  onEdit,
  onDelete,
}: {
  row: MatrixRowResponse;
  onEdit: (field: string, value: string) => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isLowConfidence = row.extraction_confidence === "low";

  return (
    <div
      className={`rounded-[14px] p-3.5 sm:p-5 animate-scale-in transition-colors hover:shadow-sm ${
        isLowConfidence ? "bg-surface-bone/50 opacity-80" : "bg-surface-card"
      }`}
      style={{ border: "1px solid var(--hairline)" }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 sm:gap-3 mb-3 sm:mb-4">
        <div className="min-w-0 flex-1 overflow-hidden">
          <h3 className="font-ui text-[14px] sm:text-[15px] font-semibold leading-[1.4] text-ink line-clamp-2 break-words">
            {row.paper_title ? <MathText text={row.paper_title} /> : "—"}
          </h3>
          {!expanded && (
            <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-4 sm:gap-x-6 gap-y-2">
              {SUMMARY_FIELDS.map((f) => (
                <div key={f.key} className="min-w-0 overflow-hidden">
                  <span className="block font-ui text-[10px] sm:text-[11px] font-semibold text-ash uppercase tracking-wide">
                    {f.label}
                  </span>
                  <span className="block font-ui text-[12px] sm:text-[13px] text-body leading-[1.5] truncate">
                    {(row[f.key] as string) || "not specified"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 sm:gap-2 shrink-0">
          {isLowConfidence && (
            <button
              onClick={onDelete}
              className="focus-ring font-ui inline-flex items-center gap-1.5 h-7 rounded-full bg-red-50 px-2.5 sm:px-3 text-[11px] sm:text-[12px] font-semibold text-red-600 hover:bg-red-100 transition-colors"
              title="Remove this low-relevance paper from the project"
            >
              <Trash size={12} weight="bold" />
              <span className="hidden sm:inline">Remove from Project</span>
              <span className="sm:hidden">Remove</span>
            </button>
          )}
          <ConfidenceBadge level={row.extraction_confidence} />
          {row.created_by === "ai" && !isLowConfidence && (
            <button
              onClick={onDelete}
              className="flex h-7 w-7 items-center justify-center rounded-full text-stone transition-all hover:bg-red-50 hover:text-error"
              title="Delete row"
            >
              <Trash size={12} weight="bold" />
            </button>
          )}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex h-7 w-7 items-center justify-center rounded-full text-ash transition-colors hover:bg-surface-bone hover:text-ink"
            title={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? <CaretUp size={14} /> : <CaretDown size={14} />}
          </button>
        </div>
      </div>

      {/* Expanded fields */}
      {expanded && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 sm:gap-y-4 pt-3 sm:pt-4 animate-slide-up" style={{ borderTop: "1px solid var(--hairline)" }}>
          {DETAIL_FIELDS.map((f) => (
            <div key={f.key} className={f.span || ""}>
              <span className="block font-ui text-[10px] sm:text-[11px] font-semibold text-ash uppercase tracking-wide mb-1">
                {f.label}
              </span>
              <EditableCell
                value={row[f.key] as string | null}
                onSave={(val) => onEdit(f.key, val)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface TableProps {
  rows: MatrixRowResponse[];
  onEdit: (rowId: string, field: string, value: string) => void;
  onDelete: (rowId: string) => void;
}

export function MatrixTable({ rows, onEdit, onDelete }: TableProps) {
  return (
    <div className="grid gap-3 sm:gap-4">
      {rows.map((row) => (
        <MatrixCard
          key={row.id}
          row={row}
          onEdit={(field, value) => onEdit(row.id, field, value)}
          onDelete={() => onDelete(row.id)}
        />
      ))}
    </div>
  );
}
