/**
 * DeepResearchTerminal - Terminal-like progress display for the Deep Research pipeline.
 *
 * Shows:
 * - Progress bar with current stage
 * - Terminal-style log entries
 * - Final report content streaming
 */

"use client";

import { useRef, useEffect } from "react";
import { useDeepResearchState } from "@/lib/stores/assistant-store";
import type { DeepResearchJobState } from "@/lib/types/assistant";
import {
  MagnifyingGlass,
  Table,
  Lightbulb,
  PencilLine,
  CircleNotch,
  CheckCircle,
  XCircle,
} from "@phosphor-icons/react";

const STAGES = [
  { key: "search", label: "Search Papers", icon: MagnifyingGlass, range: [0, 0.25] },
  { key: "matrix", label: "Generate Matrix", icon: Table, range: [0.25, 0.5] },
  { key: "gap", label: "Detect Gaps", icon: Lightbulb, range: [0.5, 0.75] },
  { key: "report", label: "Write Report", icon: PencilLine, range: [0.75, 1.0] },
] as const;

function getStageStatus(
  stageKey: string,
  state: DeepResearchJobState
): "pending" | "running" | "completed" | "failed" {
  const stageIdx = STAGES.findIndex((s) => s.key === state.stage);
  const currentIdx = STAGES.findIndex((s) => s.key === stageKey);

  if (state.status === "failed") return currentIdx <= stageIdx ? "failed" : "pending";
  if (state.status === "completed" || state.stage === "done") return "completed";
  if (currentIdx < stageIdx) return "completed";
  if (currentIdx === stageIdx) return "running";
  return "pending";
}

export function DeepResearchTerminal() {
  const state = useDeepResearchState();
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state?.logs.length]);

  if (!state) return null;

  const progressPercent = Math.round(state.progress * 100);
  const isRunning = state.status === "running";
  const isDone = state.status === "completed";
  const isFailed = state.status === "failed";

  return (
    <div className="my-4 overflow-hidden rounded-2xl border border-charcoal/10 bg-gradient-to-br from-surface-dark to-surface-deep shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-[rgba(255,255,255,0.1)]">
        <div className="flex items-center gap-2.5">
          <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${
            isRunning ? "bg-primary/20" :
            isDone ? "bg-green-500/20" :
            "bg-red-500/20"
          }`}>
            {isRunning ? (
              <CircleNotch size={16} className="text-primary animate-spin" weight="bold" />
            ) : isDone ? (
              <CheckCircle size={16} className="text-green-400" weight="fill" />
            ) : (
              <XCircle size={16} className="text-red-400" weight="fill" />
            )}
          </div>
          <div>
            <h3 className="font-ui text-sm font-semibold text-on-dark">
              {isRunning ? "Deep Research" : isDone ? "Research Complete" : "Research Failed"}
            </h3>
            <p className="font-mono text-[11px] text-on-dark-mute">
              {isRunning ? `${progressPercent}% complete` : isDone ? "100% complete" : "Error occurred"}
            </p>
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="px-5 py-3 bg-surface-deep/50">
        <div className="h-2 rounded-full bg-[rgba(255,255,255,0.1)] overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-1000 ease-out ${
              isFailed ? "bg-red-500" : "bg-gradient-to-r from-primary to-primary-deep"
            }`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        {/* Stage indicators */}
        <div className="flex items-center justify-between mt-2.5">
          {STAGES.map((stage) => {
            const status = getStageStatus(stage.key, state);
            const Icon = stage.icon;
            return (
              <div
                key={stage.key}
                className={`flex flex-col items-center gap-1 ${
                  status === "running" ? "text-primary" :
                  status === "completed" ? "text-green-400" :
                  status === "failed" ? "text-red-400" :
                  "text-on-dark-mute/40"
                }`}
              >
                <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${
                  status === "running" ? "bg-primary/20" :
                  status === "completed" ? "bg-green-500/20" :
                  status === "failed" ? "bg-red-500/20" :
                  "bg-[rgba(255,255,255,0.05)]"
                }`}>
                  {status === "running" ? (
                    <CircleNotch size={13} className="animate-spin" weight="bold" />
                  ) : status === "completed" ? (
                    <CheckCircle size={13} weight="fill" />
                  ) : (
                    <Icon size={13} />
                  )}
                </div>
                <span className="font-ui text-[10px] font-medium hidden sm:block">
                  {stage.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Terminal logs */}
      {state.logs.length > 0 && (
        <div className="px-5 py-3 max-h-[450px] overflow-y-auto bg-[#0d1117] scrollbar-thin scrollbar-thumb-charcoal">
          <div className="space-y-1">
            {state.logs.map((log, i) => (
              <div
                key={i}
                className="flex items-start gap-2.5 font-mono text-xs leading-relaxed"
              >
                <span className="text-on-dark-mute/40 shrink-0 select-none">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span className={`${
                  log.stage === "done" ? "text-green-400" :
                  log.stage === "search" ? "text-blue-400" :
                  log.stage === "matrix" ? "text-purple-400" :
                  log.stage === "gap" ? "text-yellow-400" :
                  "text-on-dark-mute"
                }`}>
                  [{log.stage}] {log.message}
                </span>
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {/* Status message */}
      {isRunning && (
        <div className="px-5 py-2.5 border-t border-[rgba(255,255,255,0.05)] bg-surface-deep/30">
          <p className="font-mono text-[11px] text-on-dark-mute truncate">
            {state.message || "Processing..."}
          </p>
        </div>
      )}
    </div>
  );
}
