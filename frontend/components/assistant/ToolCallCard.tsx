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
  Code,
  Command,
  ListBullets,
  Package,
  BookOpen,
  Terminal,
} from "@phosphor-icons/react";
import type { ChatMessageFE } from "@/lib/types";

const TOOL_META: Record<
  string,
  { label: string; icon: React.ElementType; tone: string; path: "local" | "sandbox" }
> = {
  // ── Local fast-path tools ──
  create_project: {
    label: "Create project",
    icon: FolderPlus,
    tone: "bg-violet-50 text-violet-700 border-violet-200",
    path: "local",
  },
  search_papers: {
    label: "Search papers",
    icon: MagnifyingGlass,
    tone: "bg-blue-50 text-blue-700 border-blue-200",
    path: "local",
  },
  save_paper_to_project: {
    label: "Save paper",
    icon: BookmarkSimple,
    tone: "bg-emerald-50 text-emerald-700 border-emerald-200",
    path: "local",
  },
  qa_search_papers: {
    label: "Q&A search",
    icon: Question,
    tone: "bg-sky-50 text-sky-700 border-sky-200",
    path: "local",
  },
  generate_matrix: {
    label: "Build matrix",
    icon: Table,
    tone: "bg-amber-50 text-amber-700 border-amber-200",
    path: "local",
  },
  detect_gaps: {
    label: "Detect gaps",
    icon: Lightbulb,
    tone: "bg-rose-50 text-rose-700 border-rose-200",
    path: "local",
  },
  detect_conflicts: {
    label: "Detect conflicts",
    icon: ArrowsHorizontal,
    tone: "bg-orange-50 text-orange-700 border-orange-200",
    path: "local",
  },
  generate_report: {
    label: "Write report",
    icon: FileText,
    tone: "bg-indigo-50 text-indigo-700 border-indigo-200",
    path: "local",
  },
  edit_report_section: {
    label: "Edit section",
    icon: PencilSimpleLine,
    tone: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
    path: "local",
  },
  trigger_normalization: {
    label: "Normalize PDFs",
    icon: CloudArrowUp,
    tone: "bg-teal-50 text-teal-700 border-teal-200",
    path: "local",
  },
  // ── Sandbox tools (per-project container) ──
  run_python: {
    label: "Run Python",
    icon: Code,
    tone: "bg-amber-50 text-amber-800 border-amber-200",
    path: "sandbox",
  },
  run_shell: {
    label: "Run shell",
    icon: Command,
    tone: "bg-stone-100 text-stone-800 border-stone-300",
    path: "sandbox",
  },
  read_file: {
    label: "Read file",
    icon: FileText,
    tone: "bg-blue-50 text-blue-700 border-blue-200",
    path: "sandbox",
  },
  write_file: {
    label: "Write file",
    icon: FileText,
    tone: "bg-emerald-50 text-emerald-700 border-emerald-200",
    path: "sandbox",
  },
  list_files: {
    label: "List files",
    icon: ListBullets,
    tone: "bg-cyan-50 text-cyan-700 border-cyan-200",
    path: "sandbox",
  },
  open_pdf_page: {
    label: "Open PDF page",
    icon: BookOpen,
    tone: "bg-rose-50 text-rose-700 border-rose-200",
    path: "sandbox",
  },
  grep_pdf: {
    label: "Search PDF",
    icon: MagnifyingGlass,
    tone: "bg-violet-50 text-violet-700 border-violet-200",
    path: "sandbox",
  },
  install_packages: {
    label: "pip install",
    icon: Package,
    tone: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
    path: "sandbox",
  },
};

const SANDBOX_TOOLS = new Set([
  "run_python",
  "run_shell",
  "read_file",
  "write_file",
  "list_files",
  "open_pdf_page",
  "grep_pdf",
  "install_packages",
]);

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
  if (typeof args.path === "string") return args.path;
  if (typeof args.command === "string") return args.command;
  if (Array.isArray(args.packages) && args.packages.every((p) => typeof p === "string"))
    return (args.packages as string[]).join(", ");
  if (typeof args.code === "string") {
    const first = args.code.split("\n")[0]?.trim() ?? "";
    return first ? `def … — ${first.slice(0, 60)}` : "code";
  }
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
    if (Array.isArray(parsed.matches))
      return `${parsed.matches.length} matches`;
    if (typeof parsed.exit_code === "number")
      return parsed.exit_code === 0 ? "exit 0" : `exit ${parsed.exit_code}`;
  }
  const flat = summary.replace(/\s+/g, " ").trim();
  return flat.length > 220 ? flat.slice(0, 220) + "…" : flat;
}

// ── Specialized sandbox-tool renderers ─────────────────────────────────

function StdoutStderr({ stdout, stderr }: { stdout?: string; stderr?: string }) {
  if (!stdout && !stderr) return null;
  return (
    <div className="space-y-1.5">
      {stdout && (
        <div>
          <p className="mb-0.5 font-ui text-[10px] font-semibold uppercase tracking-wide text-charcoal/60">
            stdout
          </p>
          <pre className="max-h-48 overflow-auto rounded-md border border-hairline bg-canvas p-2 font-mono text-[10.5px] text-ink/90 whitespace-pre-wrap break-words">
            {stdout}
          </pre>
        </div>
      )}
      {stderr && (
        <div>
          <p className="mb-0.5 font-ui text-[10px] font-semibold uppercase tracking-wide text-red-700">
            stderr
          </p>
          <pre className="max-h-32 overflow-auto rounded-md border border-red-200 bg-red-50/50 p-2 font-mono text-[10.5px] text-red-900 whitespace-pre-wrap break-words">
            {stderr}
          </pre>
        </div>
      )}
    </div>
  );
}

function SandboxBody({ message }: { message: ChatMessageFE }) {
  const parsed = parseSummaryJson(message.tool_summary ?? "");
  if (!parsed) {
    if (message.tool_summary) {
      return (
        <p className="whitespace-pre-wrap break-words text-ink/80">
          {message.tool_summary}
        </p>
      );
    }
    return null;
  }
  const name = message.tool_name ?? "";

  if (name === "run_python" || name === "run_shell") {
    return (
      <StdoutStderr
        stdout={typeof parsed.stdout === "string" ? parsed.stdout : ""}
        stderr={typeof parsed.stderr === "string" ? parsed.stderr : ""}
      />
    );
  }
  if (name === "read_file") {
    const content = typeof parsed.content === "string" ? parsed.content : "";
    const truncated = Boolean(parsed.truncated);
    const size = typeof parsed.size_bytes === "number" ? parsed.size_bytes : null;
    return (
      <div>
        {size != null && (
          <p className="mb-1 font-ui text-[10px] text-charcoal/60">
            {size.toLocaleString()} bytes{truncated ? " · truncated" : ""}
          </p>
        )}
        <pre className="max-h-48 overflow-auto rounded-md border border-hairline bg-canvas p-2 font-mono text-[10.5px] text-ink/90 whitespace-pre-wrap break-words">
          {content || <span className="text-charcoal/50">(empty)</span>}
        </pre>
      </div>
    );
  }
  if (name === "write_file") {
    return (
      <p className="text-ink/80">
        Wrote{" "}
        <span className="rounded bg-surface-bone px-1 font-mono text-[10.5px]">
          {String(parsed.path ?? message.tool_args?.path ?? "")}
        </span>{" "}
        ({String(parsed.size_bytes ?? 0)} bytes)
      </p>
    );
  }
  if (name === "list_files") {
    const items = Array.isArray(parsed.items) ? (parsed.items as Array<Record<string, unknown>>) : [];
    if (items.length === 0)
      return <p className="text-charcoal/60 italic">No entries.</p>;
    return (
      <ul className="space-y-0.5">
        {items.slice(0, 50).map((it, i) => (
          <li
            key={i}
            className="flex items-center gap-2 rounded border border-hairline bg-canvas px-2 py-1 font-mono text-[10.5px]"
          >
            <span className="truncate text-ink">{String(it.path ?? it.name ?? "")}</span>
            <span className="ml-auto shrink-0 text-charcoal/60">
              {it.is_dir
                ? "dir"
                : typeof it.size_bytes === "number"
                  ? `${it.size_bytes} B`
                  : ""}
            </span>
          </li>
        ))}
        {items.length > 50 && (
          <li className="text-[10px] text-charcoal/60">
            …and {items.length - 50} more
          </li>
        )}
      </ul>
    );
  }
  if (name === "open_pdf_page") {
    const content = typeof parsed.content === "string" ? parsed.content : "";
    const total = typeof parsed.total_pages === "number" ? parsed.total_pages : null;
    return (
      <div>
        {total != null && (
          <p className="mb-1 font-ui text-[10px] text-charcoal/60">
            page {String(parsed.page ?? "?")} / {total}
            {parsed.truncated ? " · truncated" : ""}
          </p>
        )}
        <pre className="max-h-56 overflow-auto rounded-md border border-hairline bg-canvas p-2 font-mono text-[10.5px] text-ink/90 whitespace-pre-wrap break-words">
          {content || <span className="text-charcoal/50">(empty page)</span>}
        </pre>
      </div>
    );
  }
  if (name === "grep_pdf") {
    const matches = Array.isArray(parsed.matches)
      ? (parsed.matches as Array<Record<string, unknown>>)
      : [];
    if (matches.length === 0)
      return <p className="text-charcoal/60 italic">No matches.</p>;
    return (
      <ul className="space-y-1.5">
        {matches.slice(0, 10).map((m, i) => (
          <li
            key={i}
            className="rounded border border-hairline bg-canvas p-2 font-mono text-[10.5px]"
          >
            <div className="mb-1 flex items-center gap-1.5 text-[9.5px] uppercase tracking-wide text-charcoal/60">
              <span>page {String(m.page ?? "?")}</span>
              <span>·</span>
              <span className="text-violet-700">/{String(m.match ?? "")}/</span>
            </div>
            <pre className="whitespace-pre-wrap break-words text-ink/85">
              {String(m.context ?? "")}
            </pre>
          </li>
        ))}
        {matches.length > 10 && (
          <li className="text-[10px] text-charcoal/60">
            …and {matches.length - 10} more matches
          </li>
        )}
      </ul>
    );
  }
  if (name === "install_packages") {
    return (
      <div>
        {Array.isArray(parsed.stdout) || typeof parsed.stdout === "string" ? (
          <pre className="max-h-40 overflow-auto rounded-md border border-hairline bg-canvas p-2 font-mono text-[10.5px] text-ink/90 whitespace-pre-wrap break-words">
            {String(parsed.stdout ?? "")}
          </pre>
        ) : null}
        {typeof parsed.stderr === "string" && parsed.stderr && (
          <pre className="mt-1.5 max-h-32 overflow-auto rounded-md border border-red-200 bg-red-50/50 p-2 font-mono text-[10.5px] text-red-900 whitespace-pre-wrap break-words">
            {parsed.stderr}
          </pre>
        )}
      </div>
    );
  }
  // Fallback: show the parsed JSON
  return (
    <pre className="max-h-40 overflow-auto font-mono text-[10.5px] whitespace-pre-wrap break-all">
      {JSON.stringify(parsed, null, 2)}
    </pre>
  );
}

export function ToolCallCard({ message }: { message: ChatMessageFE }) {
  const meta = TOOL_META[message.tool_name ?? ""] ?? {
    label: message.tool_name ?? "Tool",
    icon: CloudArrowUp,
    tone: "bg-stone-50 text-charcoal border-stone-200",
    path: "local" as const,
  };
  const Icon = meta.icon;
  const [open, setOpen] = useState(false);

  const isRunning = message.tool_status === "running";
  const isError = message.tool_status === "error";
  const isSandbox = SANDBOX_TOOLS.has(message.tool_name ?? "");

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

  const pathBadge = isSandbox ? (
    <span
      title="Executed in the per-project sandbox"
      className="inline-flex items-center gap-1 rounded-full bg-surface-dark px-2 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide text-on-dark"
    >
      <Terminal size={9} weight="bold" />
      sandbox
    </span>
  ) : null;

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
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-ui text-[12px] font-semibold text-ink">
                {meta.label}
              </span>
              {pathBadge}
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
            {isSandbox && message.tool_name === "run_python" && message.tool_args && typeof message.tool_args.code === "string" && (
              <details>
                <summary className="cursor-pointer text-[11px] font-semibold text-charcoal/80 select-none">
                  Code
                </summary>
                <pre className="mt-1.5 max-h-48 overflow-auto rounded-md border border-hairline bg-canvas p-2 font-mono text-[10.5px] text-ink/90 whitespace-pre-wrap break-words">
                  {String(message.tool_args.code)}
                </pre>
              </details>
            )}
            {isSandbox && message.tool_name === "run_shell" && message.tool_args && typeof message.tool_args.command === "string" && (
              <div>
                <p className="font-ui text-[11px] font-semibold text-charcoal/80">
                  Command
                </p>
                <pre className="mt-1 overflow-auto rounded-md border border-hairline bg-canvas p-2 font-mono text-[10.5px] text-ink/90 whitespace-pre-wrap break-words">
                  $ {String(message.tool_args.command)}
                </pre>
              </div>
            )}
            {!isSandbox &&
              message.tool_args &&
              Object.keys(message.tool_args).length > 0 && (
                <details>
                  <summary className="cursor-pointer text-[11px] font-semibold text-charcoal/80 select-none">
                    Arguments
                  </summary>
                  <pre className="mt-1.5 max-h-40 overflow-auto rounded-md bg-canvas p-2 text-[10.5px] font-mono text-ink/80 border border-hairline">
                    {JSON.stringify(message.tool_args, null, 2)}
                  </pre>
                </details>
              )}
            {isSandbox ? (
              message.tool_status === "ok" || message.tool_status === "error" ? (
                <div>
                  <p className="mb-1 font-ui text-[11px] font-semibold text-charcoal/80">
                    {isError ? "Error" : "Result"}
                  </p>
                  <SandboxBody message={message} />
                </div>
              ) : (
                <p className="text-[11px] text-charcoal/60 italic">
                  Executing in sandbox…
                </p>
              )
            ) : (
              summary && (
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
              )
            )}
            {isRunning && !summary && !isSandbox && (
              <p className="text-[11px] text-charcoal/60 italic">Executing…</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
