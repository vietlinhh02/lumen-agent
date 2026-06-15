"use client";

import { useState } from "react";
import {
  CaretDown,
  CheckCircle,
  WarningCircle,
  SpinnerGap,
  MagnifyingGlass,
  FolderPlus,
  BookmarkSimple,
  Table,
  Lightbulb,
  ArrowsHorizontal,
  FileText,
  PencilSimpleLine,
  CloudArrowUp,
  Question,
} from "@phosphor-icons/react";
import type { ChatMessageFE } from "@/lib/types";

const TOOL_META: Record<
  string,
  { label: string; icon: React.ElementType; tone: string }
> = {
  create_project: {
    label: "Create project",
    icon: FolderPlus,
    tone: "bg-violet-50 text-violet-700 border-violet-200",
  },
  search_papers: {
    label: "Search papers",
    icon: MagnifyingGlass,
    tone: "bg-blue-50 text-blue-700 border-blue-200",
  },
  save_paper_to_project: {
    label: "Save paper",
    icon: BookmarkSimple,
    tone: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
  qa_search_papers: {
    label: "Q&A search",
    icon: Question,
    tone: "bg-sky-50 text-sky-700 border-sky-200",
  },
  generate_matrix: {
    label: "Build matrix",
    icon: Table,
    tone: "bg-amber-50 text-amber-700 border-amber-200",
  },
  detect_gaps: {
    label: "Detect gaps",
    icon: Lightbulb,
    tone: "bg-rose-50 text-rose-700 border-rose-200",
  },
  detect_conflicts: {
    label: "Detect conflicts",
    icon: ArrowsHorizontal,
    tone: "bg-orange-50 text-orange-700 border-orange-200",
  },
  generate_report: {
    label: "Write report",
    icon: FileText,
    tone: "bg-indigo-50 text-indigo-700 border-indigo-200",
  },
  edit_report_section: {
    label: "Edit section",
    icon: PencilSimpleLine,
    tone: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
  },
  trigger_normalization: {
    label: "Normalize PDFs",
    icon: CloudArrowUp,
    tone: "bg-teal-50 text-teal-700 border-teal-200",
  },
};

function formatDuration(ms?: number | null) {
  if (ms == null) return null;
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function argsPreview(args: Record<string, unknown> | null | undefined): string | null {
  if (!args) return null;
  if (typeof args.query === "string") return args.query;
  if (typeof args.title === "string") return args.title;
  if (typeof args.paper_title === "string") return args.paper_title;
  if (typeof args.question === "string") return args.question;
  if (typeof args.topic === "string") return args.topic;
  if (typeof args.section_heading === "string") return args.section_heading;
  for (const v of Object.values(args)) {
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

function parseSummaryJson(summary: string | null | undefined): Record<string, unknown> | null {
  if (!summary) return null;
  try {
    const parsed = JSON.parse(summary);
    if (parsed && typeof parsed === "object") return parsed as Record<string, unknown>;
  } catch {
    // Not JSON — fall through
  }
  return null;
}

function summaryShort(summary: string | null | undefined): string {
  if (!summary) return "";
  const parsed = parseSummaryJson(summary);
  if (parsed) {
    if (typeof parsed.summary === "string") return parsed.summary;
    if (typeof parsed.message === "string") return parsed.message;
    if (typeof parsed.error === "string") return parsed.error;
    if (typeof parsed.count === "number") return `${parsed.count} results`;
    if (typeof parsed.saved === "number") return `${parsed.saved} saved`;
    if (typeof parsed.total_results === "number")
      return `${parsed.total_results} results`;
    if (Array.isArray(parsed.papers))
      return `${parsed.papers.length} papers returned`;
    if (Array.isArray(parsed.items))
      return `${parsed.items.length} items`;
  }
  const flat = summary.replace(/\s+/g, " ").trim();
  return flat.length > 220 ? flat.slice(0, 220) + "…" : flat;
}

export function ToolCallCard({ message }: { message: ChatMessageFE }) {
  const meta = TOOL_META[message.tool_name ?? ""] ?? {
    label: message.tool_name ?? "Tool",
    icon: CloudArrowUp,
    tone: "bg-stone-50 text-charcoal border-stone-200",
  };
  const Icon = meta.icon;
  const [open, setOpen] = useState(false);

  const isRunning = message.tool_status === "running";
  const isError = message.tool_status === "error";

  const statusBadge = isRunning ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700 border border-blue-200">
      <SpinnerGap size={10} className="animate-spin" />
      running
    </span>
  ) : isError ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold text-red-700 border border-red-200">
      <WarningCircle size={10} weight="fill" />
      error
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 border border-emerald-200">
      <CheckCircle size={10} weight="fill" />
      done
    </span>
  );

  const preview = argsPreview(message.tool_args);
  const summary = summaryShort(message.tool_summary);
  const duration = formatDuration(message.tool_duration_ms);

  return (
    <div className="mx-auto w-full max-w-2xl px-1 animate-fade-in">
      <div
        className={`rounded-2xl bg-surface-card border transition-all ${
          isError
            ? "border-red-200"
            : isRunning
              ? "border-blue-200 shadow-sm"
              : "border-hairline hover:border-hairline-strong"
        }`}
      >
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full text-left px-3 py-2.5 flex items-center gap-2.5"
        >
          <span
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border ${meta.tone}`}
          >
            <Icon size={14} weight="bold" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="font-ui text-[12px] font-semibold text-ink">
                {meta.label}
              </span>
              {statusBadge}
              {duration && (
                <span className="font-ui text-[10px] text-ash">· {duration}</span>
              )}
            </div>
            {preview && (
              <p className="mt-0.5 truncate font-ui text-[11px] text-charcoal/70">
                {preview}
              </p>
            )}
          </div>
          <CaretDown
            size={12}
            weight="bold"
            className={`shrink-0 text-ash transition-transform ${
              open ? "rotate-180" : ""
            }`}
          />
        </button>

        {open && (
          <div className="border-t border-hairline px-3 py-2.5 space-y-2 bg-surface-bone/40">
            {message.tool_args && Object.keys(message.tool_args).length > 0 && (
              <details>
                <summary className="cursor-pointer text-[11px] font-semibold text-charcoal/80 select-none">
                  Arguments
                </summary>
                <pre className="mt-1.5 max-h-40 overflow-auto rounded-md bg-canvas p-2 text-[10.5px] font-mono text-ink/80 border border-hairline">
                  {JSON.stringify(message.tool_args, null, 2)}
                </pre>
              </details>
            )}
            {summary && (
              <details open={isError}>
                <summary className="cursor-pointer text-[11px] font-semibold text-charcoal/80 select-none">
                  {isError ? "Error" : "Result"}
                </summary>
                <div className="mt-1.5 rounded-md bg-canvas p-2 text-[11.5px] text-ink/80 border border-hairline">
                  {parseSummaryJson(message.tool_summary ?? "") ? (
                    <pre className="max-h-40 overflow-auto font-mono text-[10.5px] whitespace-pre-wrap break-all">
                      {JSON.stringify(parseSummaryJson(message.tool_summary), null, 2)}
                    </pre>
                  ) : (
                    <p className="whitespace-pre-wrap break-words">{summary}</p>
                  )}
                </div>
              </details>
            )}
            {isRunning && !summary && (
              <p className="text-[11px] text-charcoal/60 italic">
                Executing…
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
