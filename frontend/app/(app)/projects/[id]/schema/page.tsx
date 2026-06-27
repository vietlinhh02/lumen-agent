"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowsDownUp,
  CheckCircle,
  CircleNotch,
  FloppyDisk,
  Plus,
  Robot,
  Sparkle,
  Trash,
  Warning,
} from "@phosphor-icons/react";
import { useAuthStore } from "@/lib/stores/auth-store";
import {
  getExtractionSchema,
  resetExtractionSchema,
  suggestExtractionSchema,
  updateExtractionSchema,
} from "@/lib/api/extraction-schema";
import type {
  ExtractionField,
  ExtractionFieldType,
  ExtractionSchemaResponse,
} from "@/lib/types";

// Field types accepted by the schema builder. Mirrors the backend
// vocabulary so the dropdown stays in lock-step with the JSON schema.
const FIELD_TYPES: { value: ExtractionFieldType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "enum", label: "Enum (single)" },
  { value: "multi_select", label: "Multi-select" },
  { value: "boolean", label: "Yes / No" },
  { value: "quote", label: "Verbatim quote" },
  { value: "citation", label: "Citation" },
];

// Reserved keys cannot be deleted or have their type changed. The UI
// surfaces them at the top of the list and locks the relevant inputs.
const RESERVED_KEYS: ReadonlySet<string> = new Set([
  "research_problem",
  "method",
  "dataset_or_context",
  "key_result",
  "limitation",
  "contribution",
  "relevance",
]);

function makeEmptyField(): ExtractionField {
  return {
    key: "",
    label: "",
    type: "text",
    description: null,
    required: false,
    enum_values: null,
  };
}

function fieldKeyFromLabel(label: string): string {
  return (
    label
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .replace(/^[0-9]/, "_$&")
      .slice(0, 64) || "field"
  );
}

export default function ProjectSchemaPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ?? "";
  const token = useAuthStore((s) => s.token);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [schema, setSchema] = useState<ExtractionSchemaResponse | null>(null);
  const [fields, setFields] = useState<ExtractionField[]>([]);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    if (!token || !projectId) return;
    setLoading(true);
    try {
      const data = await getExtractionSchema(token, projectId);
      setSchema(data);
      setFields(data.fields);
      setDirty(false);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to load schema",
      );
    } finally {
      setLoading(false);
    }
  }, [token, projectId]);

  useEffect(() => {
    // Defer the load call to a microtask so the effect body doesn't
    // call setState synchronously on its first run.
    queueMicrotask(() => void load());
  }, [load]);

  const custom = useMemo(
    () => fields.filter((f) => !RESERVED_KEYS.has(f.key)),
    [fields],
  );

  function updateAt(index: number, patch: Partial<ExtractionField>) {
    setFields((prev) =>
      prev.map((f, i) => (i === index ? { ...f, ...patch } : f)),
    );
    setDirty(true);
  }

  function addCustom() {
    setFields((prev) => [...prev, makeEmptyField()]);
    setDirty(true);
  }

  function removeAt(index: number) {
    const field = fields[index];
    if (!field) return;
    if (RESERVED_KEYS.has(field.key)) {
      toast.error("Reserved fields cannot be removed.");
      return;
    }
    setFields((prev) => prev.filter((_, i) => i !== index));
    setDirty(true);
  }

  function moveAt(index: number, direction: -1 | 1) {
    setFields((prev) => {
      const next = prev.slice();
      const j = index + direction;
      if (j < 0 || j >= next.length) return prev;
      [next[index], next[j]] = [next[j], next[index]];
      return next;
    });
    setDirty(true);
  }

  async function handleSave() {
    if (!token || !projectId) return;
    // Local validation: every field must have a non-empty key + label,
    // and enum/multi_select must carry a non-empty enum_values list.
    const seen = new Set<string>();
    for (let i = 0; i < fields.length; i++) {
      const f = fields[i];
      if (!f.key || !/^[a-z][a-z0-9_]*$/.test(f.key)) {
        toast.error(
          `Field #${i + 1} needs a valid key (lowercase snake_case, can't start with a digit).`,
        );
        return;
      }
      if (!f.label.trim()) {
        toast.error(`Field "${f.key}" needs a label.`);
        return;
      }
      if (seen.has(f.key)) {
        toast.error(`Duplicate key: ${f.key}`);
        return;
      }
      seen.add(f.key);
      if (
        (f.type === "enum" || f.type === "multi_select") &&
        (!f.enum_values || f.enum_values.length === 0)
      ) {
        toast.error(
          `Field "${f.key}" (${f.type}) needs at least one value.`,
        );
        return;
      }
    }
    setSaving(true);
    try {
      const next = await updateExtractionSchema(token, projectId, fields);
      setSchema(next);
      setFields(next.fields);
      setDirty(false);
      toast.success("Schema saved");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to save schema",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleSuggest() {
    if (!token || !projectId) return;
    setSuggesting(true);
    try {
      const result = await suggestExtractionSchema(token, projectId, {
        max_fields: 8,
      });
      // Merge suggested fields with reserved defaults. We never auto-apply
      // a suggestion that would change the reserved defaults — the user
      // can review and click "Save" to commit.
      const suggested = result.fields.filter(
        (f) => !RESERVED_KEYS.has(f.key),
      );
      setFields((prev) => {
        const reserved = prev.filter((f) => RESERVED_KEYS.has(f.key));
        return [...reserved, ...suggested];
      });
      setDirty(true);
      toast.success(
        `Suggested ${suggested.length} field${suggested.length === 1 ? "" : "s"} — review and save when ready.`,
      );
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to suggest fields",
      );
    } finally {
      setSuggesting(false);
    }
  }

  async function handleReset() {
    if (!token || !projectId) return;
    if (
      !confirm(
        "Reset to the seven system-default fields? This removes every custom field you added.",
      )
    ) {
      return;
    }
    setResetting(true);
    try {
      const next = await resetExtractionSchema(token, projectId);
      setSchema(next);
      setFields(next.fields);
      setDirty(false);
      toast.success("Schema reset to defaults");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to reset schema",
      );
    } finally {
      setResetting(false);
    }
  }

  if (loading && !schema) {
    return (
      <div className="w-full animate-pulse space-y-3">
        <div className="h-7 w-48 rounded bg-surface-bone" />
        <div className="h-4 w-72 rounded bg-surface-bone" />
        <div className="mt-6 h-32 rounded-[16px] bg-surface-bone" />
        <div className="h-48 rounded-[16px] bg-surface-bone" />
      </div>
    );
  }

  const versionLabel = schema?.is_default
    ? "Default schema"
    : `Custom · v${schema?.version ?? 1}`;

  return (
    <div className="animate-fade-in">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="font-display text-[20px] sm:text-[22px] font-bold leading-[1.1] text-ink">
            Extraction Schema
          </h2>
          <p className="mt-1 font-ui text-[12px] text-charcoal">
            Define the typed fields the AI will extract for every paper.
            The seven defaults are immutable; add custom fields for
            domain-specific evidence (PICO, ML benchmark, etc.).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 self-start">
          <span
            className={`font-ui inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              schema?.is_default
                ? "bg-ash/10 text-ash"
                : "bg-primary/10 text-primary"
            }`}
          >
            <CheckCircle size={12} weight="fill" />
            {versionLabel}
          </span>
          <button
            type="button"
            onClick={handleSuggest}
            disabled={suggesting || saving || resetting}
            className="focus-ring font-ui inline-flex h-[34px] items-center gap-1.5 rounded-full bg-primary/10 px-3 text-[12px] font-semibold text-primary hover:bg-primary/20 transition-colors active:scale-95 disabled:opacity-50"
          >
            {suggesting ? (
              <CircleNotch size={12} className="animate-spin" />
            ) : (
              <Sparkle size={12} weight="fill" />
            )}
            Suggest fields
          </button>
          <button
            type="button"
            onClick={handleReset}
            disabled={resetting || saving || suggesting}
            className="focus-ring font-ui inline-flex h-[34px] items-center gap-1.5 rounded-full bg-surface-bone px-3 text-[12px] font-semibold text-charcoal hover:bg-ash/15 transition-colors active:scale-95 disabled:opacity-50"
          >
            {resetting ? (
              <CircleNotch size={12} className="animate-spin" />
            ) : (
              <Warning size={12} />
            )}
            Reset to defaults
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !dirty}
            className="focus-ring font-ui inline-flex h-[34px] items-center gap-1.5 rounded-full bg-primary px-4 text-[12px] font-semibold text-on-primary hover:bg-primary-deep transition-colors active:scale-95 disabled:opacity-50"
          >
            {saving ? (
              <CircleNotch size={12} className="animate-spin" />
            ) : (
              <FloppyDisk size={12} weight="fill" />
            )}
            Save schema
          </button>
        </div>
      </div>

      {dirty && (
        <div className="mb-4 rounded-[12px] border border-yellow-200 bg-yellow-50 px-3 py-2 text-[12px] text-yellow-800">
          You have unsaved changes. They will only take effect for future
          matrix extractions.
        </div>
      )}

      <div className="rounded-[16px] border border-hairline bg-surface-card p-4 sm:p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-ui text-[14px] font-semibold text-ink">
            Custom fields ({custom.length})
          </h3>
          <button
            type="button"
            onClick={addCustom}
            className="focus-ring font-ui inline-flex h-[32px] items-center gap-1.5 rounded-full bg-primary px-3 text-[12px] font-semibold text-on-primary hover:bg-primary-deep transition-colors active:scale-95"
          >
            <Plus size={12} weight="bold" />
            Add field
          </button>
        </div>

        {custom.length === 0 ? (
          <div className="rounded-[12px] border border-dashed border-hairline-strong bg-surface-bone/50 px-4 py-6 text-center">
            <Robot
              size={24}
              weight="duotone"
              className="mx-auto mb-2 text-ash"
            />
            <p className="font-ui text-[13px] font-semibold text-ink">
              No custom fields yet
            </p>
            <p className="mt-1 font-ui text-[12px] text-charcoal">
              Add a field manually, or click <em>Suggest fields</em> to
              let the LLM propose typed columns based on this project&apos;s
              topic and saved papers.
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {custom.map((f) => {
              const realIndex = fields.findIndex((ff) => ff.key === f.key);
              return (
                <FieldRow
                  key={`${f.key}-${realIndex}`}
                  field={f}
                  index={realIndex}
                  isReserved={false}
                  onUpdate={updateAt}
                  onRemove={removeAt}
                  onMove={moveAt}
                />
              );
            })}
          </ul>
        )}
      </div>

      <p className="mt-4 font-ui text-[11px] text-ash">
        Existing matrix rows keep their stored values; future
        re-generations will use the new schema. To re-extract from
        scratch, use the Matrix tab.
      </p>
    </div>
  );
}

interface FieldRowProps {
  field: ExtractionField;
  index: number;
  isReserved: boolean;
  onUpdate: (index: number, patch: Partial<ExtractionField>) => void;
  onRemove: (index: number) => void;
  onMove: (index: number, direction: -1 | 1) => void;
}

function FieldRow({
  field,
  index,
  isReserved,
  onUpdate,
  onRemove,
  onMove,
}: FieldRowProps) {
  const [enumDraft, setEnumDraft] = useState(
    (field.enum_values ?? []).join(", "),
  );
  useEffect(() => {
    // Defer the sync to a microtask to avoid setState-during-effect
    // warnings when the parent schema reloads.
    const next = (field.enum_values ?? []).join(", ");
    queueMicrotask(() => setEnumDraft(next));
  }, [field.enum_values]);

  const needsEnum =
    field.type === "enum" || field.type === "multi_select";
  const isValidKey = /^[a-z][a-z0-9_]*$/.test(field.key);
  const showKeyError = !isReserved && field.key !== "" && !isValidKey;

  return (
    <li
      className={`rounded-[12px] border p-3 ${
        isReserved
          ? "border-hairline bg-surface-bone/40"
          : "border-hairline bg-canvas"
      }`}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-12">
        <div className="sm:col-span-3">
          <label className="block font-ui text-[10px] font-semibold uppercase tracking-wide text-ash">
            Label
          </label>
          <input
            value={field.label}
            disabled={isReserved}
            onChange={(e) => {
              const next = e.target.value;
              onUpdate(index, {
                label: next,
                key: isReserved ? field.key : field.key || fieldKeyFromLabel(next),
              });
            }}
            placeholder="e.g. Sample size"
            className="mt-1 w-full rounded-[8px] border border-hairline bg-surface-card px-2.5 py-1.5 font-ui text-[13px] text-ink disabled:bg-surface-bone disabled:text-charcoal"
          />
        </div>

        <div className="sm:col-span-3">
          <label className="block font-ui text-[10px] font-semibold uppercase tracking-wide text-ash">
            Key
          </label>
          <input
            value={field.key}
            disabled={isReserved}
            onChange={(e) => onUpdate(index, { key: e.target.value })}
            placeholder="sample_size"
            className={`mt-1 w-full rounded-[8px] border bg-surface-card px-2.5 py-1.5 font-mono text-[12px] ${
              showKeyError
                ? "border-red-400 text-red-700"
                : "border-hairline text-ink"
            } disabled:bg-surface-bone disabled:text-charcoal`}
          />
          {showKeyError && (
            <p className="mt-1 font-ui text-[10px] text-red-600">
              Lowercase snake_case, can&apos;t start with a digit.
            </p>
          )}
        </div>

        <div className="sm:col-span-3">
          <label className="block font-ui text-[10px] font-semibold uppercase tracking-wide text-ash">
            Type
          </label>
          <select
            value={field.type}
            disabled={isReserved}
            onChange={(e) =>
              onUpdate(index, {
                type: e.target.value as ExtractionFieldType,
                enum_values: needsEnumOrType(e.target.value)
                  ? field.enum_values
                  : null,
              })
            }
            className="mt-1 w-full rounded-[8px] border border-hairline bg-surface-card px-2 py-1.5 font-ui text-[13px] text-ink disabled:bg-surface-bone disabled:text-charcoal"
          >
            {FIELD_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-end justify-end gap-1 sm:col-span-3">
          <button
            type="button"
            onClick={() => onMove(index, -1)}
            disabled={isReserved}
            className="flex h-7 w-7 items-center justify-center rounded-full text-ash hover:bg-surface-bone hover:text-ink disabled:opacity-30"
            title="Move up"
          >
            <ArrowsDownUp size={14} className="-rotate-90" />
          </button>
          <button
            type="button"
            onClick={() => onMove(index, 1)}
            disabled={isReserved}
            className="flex h-7 w-7 items-center justify-center rounded-full text-ash hover:bg-surface-bone hover:text-ink disabled:opacity-30"
            title="Move down"
          >
            <ArrowsDownUp size={14} className="rotate-90" />
          </button>
          {!isReserved && (
            <button
              type="button"
              onClick={() => onRemove(index)}
              className="flex h-7 w-7 items-center justify-center rounded-full text-ash hover:bg-red-50 hover:text-red-600"
              title="Remove field"
            >
              <Trash size={14} />
            </button>
          )}
        </div>

        <div className="sm:col-span-12">
          <label className="block font-ui text-[10px] font-semibold uppercase tracking-wide text-ash">
            Description (optional)
          </label>
          <input
            value={field.description ?? ""}
            onChange={(e) => onUpdate(index, { description: e.target.value || null })}
            placeholder="What should the AI look for in this field?"
            className="mt-1 w-full rounded-[8px] border border-hairline bg-surface-card px-2.5 py-1.5 font-ui text-[13px] text-ink"
          />
        </div>

        <div className="flex items-center gap-3 sm:col-span-8">
          <label className="flex items-center gap-1.5 font-ui text-[12px] text-charcoal">
            <input
              type="checkbox"
              checked={field.required}
              disabled={isReserved}
              onChange={(e) => onUpdate(index, { required: e.target.checked })}
              className="h-3.5 w-3.5 accent-primary"
            />
            Required
          </label>
        </div>

        {needsEnum && (
          <div className="sm:col-span-12">
            <label className="block font-ui text-[10px] font-semibold uppercase tracking-wide text-ash">
              Values (comma-separated)
            </label>
            <input
              value={enumDraft}
              onChange={(e) => setEnumDraft(e.target.value)}
              onBlur={() => {
                const values = enumDraft
                  .split(",")
                  .map((v) => v.trim())
                  .filter(Boolean);
                onUpdate(index, { enum_values: values });
              }}
              placeholder="e.g. RCT, cohort, case_study"
              className="mt-1 w-full rounded-[8px] border border-hairline bg-surface-card px-2.5 py-1.5 font-ui text-[13px] text-ink"
            />
            {field.enum_values && field.enum_values.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {field.enum_values.map((v) => (
                  <span
                    key={v}
                    className="font-ui inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary"
                  >
                    {v}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function needsEnumOrType(type: string): boolean {
  return type === "enum" || type === "multi_select";
}
