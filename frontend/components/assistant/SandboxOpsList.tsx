"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";
import { useMemo } from "react";
import {
  CheckCircle,
  Code,
  Command,
  FileText,
  ListBullets,
  MagnifyingGlass,
  Package,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import type { ChatMessageFE } from "@/lib/types";

const ICONS: Record<string, React.ElementType> = {
  run_python: Code,
  run_shell: Command,
  read_file: FileText,
  write_file: FileText,
  list_files: ListBullets,
  open_pdf_page: FileText,
  grep_pdf: MagnifyingGlass,
  install_packages: Package,
};

const TONE: Record<string, string> = {
  run_python: "text-amber-700",
  run_shell: "text-stone-700",
  read_file: "text-blue-700",
  write_file: "text-emerald-700",
  list_files: "text-cyan-700",
  open_pdf_page: "text-rose-700",
  grep_pdf: "text-violet-700",
  install_packages: "text-fuchsia-700",
};

function fmtRel(ts: number): string {
  const sec = Math.max(1, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  return `${Math.round(sec / 3600)}h ago`;
}

export function SandboxOpsList() {
  const messages = useAssistantStore((s) => s.state.messages);
  const lastTool = useAssistantStore((s) => s.state.sandboxLastTool);

  const ops: ChatMessageFE[] = useMemo(
    () =>
      messages
        .filter(
          (m): m is ChatMessageFE & { tool_name: string } =>
            m.role === "tool_log" &&
            !!m.tool_name &&
            [
              "run_python",
              "run_shell",
              "read_file",
              "write_file",
              "list_files",
              "open_pdf_page",
              "grep_pdf",
              "install_packages",
            ].includes(m.tool_name),
        )
        .slice(-30)
        .reverse(),
    [messages],
  );

  if (ops.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-hairline px-3 py-4 text-center text-[11px] text-charcoal/60">
        No sandbox operations yet this session. The agent uses these for Python,
        shell, file I/O, PDF inspection, and pip install.
      </div>
    );
  }
  return (
    <ol className="space-y-1">
      {ops.map((op, i) => {
        const Icon = ICONS[op.tool_name ?? ""] ?? Code;
        const tone = TONE[op.tool_name ?? ""] ?? "text-charcoal";
        const isRunning = op.tool_status === "running";
        const isError = op.tool_status === "error";
        return (
          <li
            key={i}
            className="flex items-center gap-2 rounded border border-hairline bg-canvas px-2 py-1.5 text-[11px]"
          >
            <Icon size={12} weight="bold" className={tone} />
            <span className="font-mono text-ink">{op.tool_name}</span>
            <span className="text-charcoal/50">·</span>
            <span className="truncate font-mono text-[10.5px] text-charcoal">
              {argSummary(op)}
            </span>
            <span className="ml-auto flex shrink-0 items-center gap-1.5">
              {op.tool_duration_ms != null && (
                <span className="font-mono text-[10px] text-ash">
                  {op.tool_duration_ms < 1000
                    ? `${op.tool_duration_ms} ms`
                    : `${(op.tool_duration_ms / 1000).toFixed(1)} s`}
                </span>
              )}
              {isRunning ? (
                <span className="rounded-full bg-blue-50 px-1.5 py-0.5 text-[9.5px] font-semibold text-blue-700 border border-blue-200">
                  running
                </span>
              ) : isError ? (
                <WarningCircle size={11} weight="fill" className="text-red-600" />
              ) : (
                <CheckCircle size={11} weight="fill" className="text-emerald-600" />
              )}
            </span>
          </li>
        );
      })}
      {lastTool && (
        <li className="flex items-center gap-1.5 px-1 text-[10px] text-charcoal/60">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          last sandbox tool:&nbsp;
          <span className="font-mono">{lastTool.name}</span>
          &nbsp;{fmtRel(lastTool.ts)}
        </li>
      )}
    </ol>
  );
}

function argSummary(op: ChatMessageFE): string {
  const a = op.tool_args;
  if (!a) return "";
  if (typeof a.path === "string") return a.path;
  if (typeof a.command === "string") return a.command;
  if (typeof a.code === "string") {
    const first = a.code.split("\n")[0]?.slice(0, 60) ?? "";
    return first || "code";
  }
  if (Array.isArray(a.packages)) return a.packages.join(", ");
  if (typeof a.pattern === "string") return `/${a.pattern}/`;
  return "";
}

// `XCircle` is intentionally imported so future code can mark a still-
// failing op explicitly without an extra edit; keep the symbol live.
void XCircle;
