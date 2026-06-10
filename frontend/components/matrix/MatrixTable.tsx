"use client";

import { useState } from "react";
import { CaretDown, CaretUp, Trash } from "@phosphor-icons/react";
import type { MatrixRowResponse, MatrixRowUpdate } from "@/lib/types";
import { EditableCell } from "./EditableCell";
import { ConfidenceBadge } from "./ConfidenceBadge";

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

  return (
    <div
      className="rounded-[14px] bg-surface-card p-5 animate-scale-in transition-colors hover:shadow-sm"
      style={{ border: "1px solid var(--hairline)" }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0 flex-1">
          <h3 className="font-ui text-[15px] font-semibold leading-[1.4] text-ink line-clamp-2">
            {row.paper_title || "—"}
          </h3>
          {!expanded && (
            <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
              {SUMMARY_FIELDS.map((f) => (
                <div key={f.key} className="min-w-0">
                  <span className="block font-ui text-[11px] font-semibold text-ash uppercase tracking-wide">
                    {f.label}
                  </span>
                  <span className="block font-ui text-[13px] text-body leading-[1.5] line-clamp-1">
                    {(row[f.key] as string) || "not specified"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <ConfidenceBadge level={row.extraction_confidence} />
          {row.created_by === "ai" && (
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
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4 pt-4 animate-slide-up" style={{ borderTop: "1px solid var(--hairline)" }}>
          {DETAIL_FIELDS.map((f) => (
            <div key={f.key} className={f.span || ""}>
              <span className="block font-ui text-[11px] font-semibold text-ash uppercase tracking-wide mb-1">
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
    <div className="grid gap-4">
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
