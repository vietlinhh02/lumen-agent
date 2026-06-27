"use client";

import { useEffect, useState } from "react";
import { Check, X } from "@phosphor-icons/react";
import type { ExtractionField } from "@/lib/types";

type CellValue = string | number | boolean | string[] | null;

interface Props {
  value: CellValue;
  field: ExtractionField;
  onSave: (value: CellValue) => void;
  multiline?: boolean;
  className?: string;
}

/** A type-aware cell editor for matrix rows.
 *
 * Picks the right widget for the field's type (``text``/``quote``/
 * ``citation`` → textarea, ``number`` → number input, ``boolean`` → toggle,
 * ``enum`` → dropdown, ``multi_select`` → chip selector). Keyboard
 * confirm (Enter) and Esc cancel behave like the legacy text cell so
 * existing muscle memory still works.
 */
export function TypedCell({
  value,
  field,
  onSave,
  multiline,
  className = "",
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<CellValue>(value);

  useEffect(() => {
    if (!editing) queueMicrotask(() => setDraft(value));
  }, [value, editing]);

  if (!editing) {
    return (
      <span
        onClick={() => {
          setDraft(value);
          setEditing(true);
        }}
        className={`block cursor-pointer rounded-[4px] px-1 py-0.5 font-ui text-[13px] leading-[1.5] transition-colors hover:bg-surface-bone ${className}`}
      >
        {renderDisplay(value, field)}
      </span>
    );
  }

  return (
    <div
      className={`flex flex-col gap-1 ${className}`}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          setDraft(value);
          setEditing(false);
        } else if (e.key === "Enter") {
          if (field.type === "text" || field.type === "quote" || field.type === "citation" || field.type === "number") {
            if (!multiline && !e.shiftKey && field.type !== "text") {
              e.preventDefault();
              commit();
            } else if (field.type === "text" && !e.shiftKey) {
              e.preventDefault();
              commit();
            }
          }
        }
      }}
    >
      {renderEditor(field, draft, setDraft)}
      <div className="flex items-center justify-end gap-1">
        <button
          type="button"
          onClick={() => {
            setDraft(value);
            setEditing(false);
          }}
          className="flex h-6 w-6 items-center justify-center rounded-full text-ash hover:bg-surface-bone hover:text-ink"
          title="Cancel"
        >
          <X size={12} />
        </button>
        <button
          type="button"
          onClick={commit}
          className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-on-primary hover:bg-primary-deep"
          title="Save"
        >
          <Check size={12} weight="bold" />
        </button>
      </div>
    </div>
  );

  function commit() {
    setEditing(false);
    if (draft !== value) onSave(draft);
  }
}

function renderDisplay(value: CellValue, field: ExtractionField): React.ReactNode {
  if (value === null || value === undefined || value === "") {
    return (
      <span className="text-stone italic">not specified</span>
    );
  }
  switch (field.type) {
    case "boolean":
      return (
        <span className="font-ui inline-flex items-center gap-1.5">
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${
              value ? "bg-green-500" : "bg-ash"
            }`}
          />
          {value ? "Yes" : "No"}
        </span>
      );
    case "multi_select":
      if (Array.isArray(value)) {
        if (value.length === 0) {
          return <span className="text-stone italic">not specified</span>;
        }
        return (
          <span className="flex flex-wrap gap-1">
            {value.map((v) => (
              <span
                key={v}
                className="font-ui rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary"
              >
                {v}
              </span>
            ))}
          </span>
        );
      }
      return String(value);
    case "number":
      return (
        <span className="font-mono text-[12px]">
          {typeof value === "number" ? value.toLocaleString() : String(value)}
        </span>
      );
    case "enum":
      return (
        <span className="font-ui inline-flex items-center gap-1.5">
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
            {String(value)}
          </span>
        </span>
      );
    case "quote":
      return (
        <span className="italic text-body">“{String(value)}”</span>
      );
    case "citation":
      return (
        <span className="font-mono text-[12px] text-charcoal">
          [{String(value)}]
        </span>
      );
    default:
      return <span className="text-body">{String(value)}</span>;
  }
}

function renderEditor(
  field: ExtractionField,
  draft: CellValue,
  setDraft: (v: CellValue) => void,
) {
  switch (field.type) {
    case "boolean":
      return (
        <label className="flex items-center gap-2 font-ui text-[12px]">
          <input
            type="checkbox"
            autoFocus
            checked={Boolean(draft)}
            onChange={(e) => setDraft(e.target.checked)}
            className="h-4 w-4 accent-primary"
          />
          {draft ? "Yes" : "No"}
        </label>
      );
    case "number":
      return (
        <input
          type="number"
          autoFocus
          value={
            typeof draft === "number"
              ? draft
              : typeof draft === "string"
                ? draft
                : ""
          }
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") {
              setDraft(null);
            } else {
              const num = Number(raw);
              setDraft(Number.isFinite(num) ? num : null);
            }
          }}
          className="focus-ring w-full rounded-[8px] border border-hairline bg-surface-card px-2 py-1 font-mono text-[13px] outline-none focus:border-primary"
        />
      );
    case "enum":
      return (
        <select
          autoFocus
          value={typeof draft === "string" ? draft : ""}
          onChange={(e) => setDraft(e.target.value || null)}
          className="focus-ring w-full rounded-[8px] border border-hairline bg-surface-card px-2 py-1 font-ui text-[13px] outline-none focus:border-primary"
        >
          <option value="">— unset —</option>
          {(field.enum_values ?? []).map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      );
    case "multi_select":
      return (
        <MultiSelect
          autoFocus
          options={field.enum_values ?? []}
          value={Array.isArray(draft) ? draft : []}
          onChange={(vals) => setDraft(vals)}
        />
      );
    case "quote":
    case "citation":
    case "text":
    default:
      return (
        <textarea
          autoFocus
          value={
            typeof draft === "string"
              ? draft
              : typeof draft === "number"
                ? String(draft)
                : ""
          }
          onChange={(e) => setDraft(e.target.value || null)}
          rows={field.type === "text" ? 3 : 2}
          className="focus-ring w-full resize-y rounded-[8px] border border-hairline bg-surface-card px-2 py-1 font-ui text-[13px] outline-none focus:border-primary"
        />
      );
  }
}

interface MultiSelectProps {
  options: string[];
  value: string[];
  onChange: (next: string[]) => void;
  autoFocus?: boolean;
}

function MultiSelect({ options, value, onChange, autoFocus }: MultiSelectProps) {
  return (
    <div className="flex flex-wrap gap-1">
      {options.map((opt) => {
        const selected = value.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            autoFocus={autoFocus && opt === value[0]}
            onClick={() => {
              const next = selected
                ? value.filter((v) => v !== opt)
                : [...value, opt];
              onChange(next);
            }}
            className={`font-ui rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
              selected
                ? "bg-primary text-on-primary"
                : "bg-surface-bone text-charcoal hover:bg-primary/15 hover:text-primary"
            }`}
          >
            {selected ? "✓ " : ""}
            {opt}
          </button>
        );
      })}
    </div>
  );
}
