"use client";

import { useMemo, useState } from "react";
import { CaretDown, CaretUp, Funnel, Quotes, Trash } from "@phosphor-icons/react";
import type {
  ExtractionField,
  ExtractionSchemaResponse,
  MatrixRowResponse,
  MatrixRowUpdate,
} from "@/lib/types";
import { EditableCell } from "./EditableCell";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { MathText } from "../search/MathText";
import { TypedCell } from "./TypedCell";

// Reserved fields always surface at the top, in this canonical order.
const RESERVED_FIELDS: { key: keyof MatrixRowUpdate; label: string; span?: string }[] = [
  { key: "research_problem", label: "Research Problem", span: "md:col-span-2" },
  { key: "method", label: "Method", span: "md:col-span-2" },
  { key: "dataset_or_context", label: "Dataset / Context" },
  { key: "key_result", label: "Key Result", span: "md:col-span-2" },
  { key: "limitation", label: "Limitation" },
  { key: "contribution", label: "Contribution", span: "md:col-span-2" },
  { key: "relevance", label: "Relevance", span: "md:col-span-2" },
];

const SUMMARY_FIELDS: { key: keyof MatrixRowUpdate; label: string }[] = [
  { key: "method", label: "Method" },
  { key: "key_result", label: "Key Result" },
];

type EditValue = string | number | boolean | string[] | null;

interface Props {
  rows: MatrixRowResponse[];
  schema: ExtractionSchemaResponse | null;
  filteredRowIds?: Set<string> | null;
  onEdit: (rowId: string, field: string, value: EditValue) => void;
  onDelete: (rowId: string) => void;
  onViewEvidence?: (rowId: string) => void;
}

export function MatrixTable({
  rows,
  schema,
  filteredRowIds,
  onEdit,
  onDelete,
  onViewEvidence,
}: Props) {
  // Apply an optional filter (from the matrix:filter endpoint) on top
  // of the server-side list. `null` means "no filter — show all".
  const visibleRows = useMemo(() => {
    if (!filteredRowIds) return rows;
    return rows.filter((r) => filteredRowIds.has(r.id));
  }, [rows, filteredRowIds]);

  if (visibleRows.length === 0 && filteredRowIds) {
    return (
      <div className="rounded-[16px] border border-dashed border-hairline bg-surface-bone/40 px-4 py-8 text-center">
        <p className="font-ui text-[14px] font-semibold text-ink">
          No rows match the current filter.
        </p>
        <p className="mt-1 font-ui text-[12px] text-charcoal">
          Clear the filter to see every row again.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:gap-4">
      {visibleRows.map((row) => (
        <MatrixCard
          key={row.id}
          row={row}
          schema={schema}
          onEdit={(field, value) => onEdit(row.id, field, value)}
          onDelete={() => onDelete(row.id)}
          onViewEvidence={onViewEvidence ? () => onViewEvidence(row.id) : undefined}
        />
      ))}
    </div>
  );
}

function MatrixCard({
  row,
  schema,
  onEdit,
  onDelete,
  onViewEvidence,
}: {
  row: MatrixRowResponse;
  schema: ExtractionSchemaResponse | null;
  onEdit: (field: string, value: EditValue) => void;
  onDelete: () => void;
  onViewEvidence?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isLowConfidence = row.extraction_confidence === "low";

  // Build the list of fields to render. We always show the seven reserved
  // fields; custom fields are appended in the order declared in the schema.
  const fields = useMemo<ExtractionField[]>(() => {
    const reservedEntries: ExtractionField[] = RESERVED_FIELDS.map((r) => ({
      key: r.key,
      label: r.label,
      type: "text",
      description: null,
      required: false,
      enum_values: null,
    }));
    const customEntries: ExtractionField[] = (schema?.fields ?? []).filter(
      (f) => !RESERVED_FIELDS.some((r) => r.key === f.key),
    );
    return [...reservedEntries, ...customEntries];
  }, [schema?.fields]);

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
          {onViewEvidence && (
          <button
            onClick={onViewEvidence}
            className="flex h-7 w-7 items-center justify-center rounded-full text-ash transition-colors hover:bg-violet-50 hover:text-violet-600"
            title="View supporting evidence"
          >
            <Quotes size={14} weight="bold" />
          </button>
          )}
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
        <div className="pt-3 sm:pt-4 animate-slide-up" style={{ borderTop: "1px solid var(--hairline)" }}>
          <div className="mb-3">
            <span className="font-ui text-[11px] font-semibold uppercase tracking-wide text-ash">
              Editable fields
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 sm:gap-y-4">
            {fields.map((f) => {
                const isReserved = RESERVED_FIELDS.some((r) => r.key === f.key);
                return (
                  <div
                    key={f.key}
                    className={
                      RESERVED_FIELDS.find((r) => r.key === f.key)?.span ?? ""
                    }
                  >
                    <span className="mb-1 flex items-center gap-1.5 font-ui text-[10px] sm:text-[11px] font-semibold text-ash uppercase tracking-wide">
                      {f.label}
                      {!isReserved && (
                        <span
                          title="Custom field"
                          className="font-ui rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold text-primary"
                        >
                          custom
                        </span>
                      )}
                      {f.required && (
                        <span className="font-ui text-[10px] text-red-600">
                          *
                        </span>
                      )}
                    </span>
                    {isReserved ? (
                      <EditableCell
                        value={row[f.key as keyof MatrixRowResponse] as string | null}
                        onSave={(val) => onEdit(f.key, val)}
                      />
                    ) : (
                      <TypedCell
                        field={f}
                        value={(row.custom_fields ?? {})[f.key] as EditValue}
                        onSave={(val) => onEdit(f.key, val)}
                      />
                    )}
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}

// Re-export so other components (the matrix page) can render the same
// "no rows match filter" empty state.
export function MatrixEmptyFilterState() {
  return (
    <div className="rounded-[16px] border border-dashed border-hairline bg-surface-bone/40 px-4 py-8 text-center">
      <Funnel size={20} className="mx-auto mb-2 text-ash" />
      <p className="font-ui text-[14px] font-semibold text-ink">
        No rows match the current filter.
      </p>
      <p className="mt-1 font-ui text-[12px] text-charcoal">
        Clear the filter to see every row again.
      </p>
    </div>
  );
}
