/**
 * IterationPanel - Replaces PlanPanel for ReAct agent.
 * 
 * Shows:
 * - Current iteration n/max
 * - Current phase (reasoning/acting)
 * - Last tool used
 * - Progress through iterations
 */

"use client";

import { useState } from "react";
import { useCurrentIteration, useLastToolUsed, useThoughtBuffers } from "@/lib/stores/assistant-store";
import {
  ArrowCounterClockwise,
  Brain,
  CaretDown,
  CaretUp,
  Gear,
  Lightning,
  Spinner,
} from "@phosphor-icons/react";

interface IterationPanelProps {
  /** Optional title for the panel */
  title?: string;
}

export function IterationPanel({ title = "Agent Progress" }: IterationPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const { iteration, max, phase } = useCurrentIteration();
  const lastToolUsed = useLastToolUsed();
  const thoughtBuffers = useThoughtBuffers();

  // Calculate progress
  const progressPercent = max > 0 ? ((iteration + 1) / max) * 100 : 0;
  const hasProgress = iteration > 0 || phase !== null;

  return (
    <div className="rounded-xl border border-charcoal/20 bg-surface-card overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between px-4 py-3 hover:bg-surface-bone/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${
            phase === "reasoning" 
              ? "bg-primary/10" 
              : phase === "acting"
              ? "bg-green-500/10"
              : "bg-surface-bone"
          }`}>
            {phase === "reasoning" ? (
              <Brain size={16} weight="fill" className="text-primary animate-pulse" />
            ) : phase === "acting" ? (
              <Gear size={16} weight="fill" className="text-green-600 animate-spin" style={{ animationDuration: "2s" }} />
            ) : (
              <Lightning size={16} weight="fill" className="text-primary" />
            )}
          </div>
          <div className="text-left">
            <p className="font-ui text-sm font-medium text-ink">
              {title}
            </p>
            <p className="font-ui text-xs text-charcoal">
              {phase === null && "Idle"}
              {phase === "reasoning" && "Analyzing…"}
              {phase === "acting" && "Executing tools…"}
              {lastToolUsed && phase === "acting" && ` · ${lastToolUsed}`}
            </p>
          </div>
        </div>
        {isExpanded ? (
          <CaretUp size={16} className="text-charcoal" />
        ) : (
          <CaretDown size={16} className="text-charcoal" />
        )}
      </button>

      {/* Progress bar */}
      {hasProgress && (
        <div className="h-1 bg-charcoal/10">
          <div
            className={`h-full transition-all duration-500 ${
              phase === "reasoning" 
                ? "bg-primary" 
                : phase === "acting"
                ? "bg-green-500"
                : "bg-charcoal/30"
            }`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      )}

      {/* Content */}
      {isExpanded && (
        <div className="p-3 pt-2">
          {/* Iteration counter */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <span className="font-ui text-[10px] font-semibold uppercase tracking-wider text-charcoal/50">
                Iteration
              </span>
              <span className="font-ui text-xs font-medium text-ink">
                {Math.max(1, iteration + 1)} / {max}
              </span>
            </div>
            
            {/* Iteration dots */}
            <div className="flex gap-1">
              {Array.from({ length: Math.min(max, 15) }, (_, i) => (
                <div
                  key={i}
                  className={`h-2 w-2 rounded-full transition-all ${
                    i < iteration
                      ? "bg-green-500"
                      : i === iteration && phase !== null
                      ? phase === "reasoning"
                        ? "bg-primary animate-pulse"
                        : "bg-green-500 animate-pulse"
                      : "bg-charcoal/20"
                  }`}
                />
              ))}
              {max > 15 && (
                <span className="ml-1 font-ui text-[10px] text-charcoal/50">
                  +{max - 15}
                </span>
              )}
            </div>
          </div>

          {/* Phase indicator */}
          <div className="mb-3 flex items-center gap-2">
            <span className="font-ui text-[10px] font-semibold uppercase tracking-wider text-charcoal/50">
              Phase
            </span>
            <div className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 ${
              phase === "reasoning"
                ? "bg-primary/10"
                : phase === "acting"
                ? "bg-green-500/10"
                : "bg-surface-bone"
            }`}>
              {phase === "reasoning" ? (
                <>
                  <Brain size={10} className="text-primary" />
                  <span className="font-ui text-[10px] font-medium text-primary">
                    Reasoning
                  </span>
                </>
              ) : phase === "acting" ? (
                <>
                  <Gear size={10} className="text-green-600" />
                  <span className="font-ui text-[10px] font-medium text-green-600">
                    Acting
                  </span>
                </>
              ) : (
                <>
                  <Spinner size={10} className="text-charcoal/40" />
                  <span className="font-ui text-[10px] font-medium text-charcoal/40">
                    Waiting
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Last tool used */}
          {lastToolUsed && (
            <div className="mb-3 flex items-center gap-2">
              <span className="font-ui text-[10px] font-semibold uppercase tracking-wider text-charcoal/50">
                Last Tool
              </span>
              <span className="rounded bg-canvas px-1.5 py-0.5 font-mono text-[10px] text-charcoal">
                {lastToolUsed}
              </span>
            </div>
          )}

          {/* Previous thoughts summary */}
          {thoughtBuffers.size > 0 && (
            <div>
              <span className="mb-2 block font-ui text-[10px] font-semibold uppercase tracking-wider text-charcoal/50">
                Thoughts
              </span>
              <div className="space-y-1.5">
                {Array.from(thoughtBuffers.entries()).slice(-3).map(([iter, thought]) => (
                  <div
                    key={iter}
                    className="flex items-start gap-2 rounded-lg bg-canvas/50 px-2 py-1.5"
                  >
                    <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-medium ${
                      iter === iteration 
                        ? "bg-primary text-white" 
                        : "bg-charcoal/20 text-charcoal/60"
                    }`}>
                      {iter + 1}
                    </span>
                    <p className="line-clamp-2 font-mono text-[10px] leading-relaxed text-charcoal/70 italic">
                      {thought.slice(-80)}
                      {thought.length > 80 && "…"}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* No activity yet */}
          {!hasProgress && thoughtBuffers.size === 0 && (
            <div className="flex flex-col items-center justify-center py-4 text-center">
              <ArrowCounterClockwise size={24} className="mb-2 text-charcoal/30" />
              <p className="font-ui text-xs text-charcoal/50">
                No activity yet
              </p>
              <p className="mt-1 font-ui text-[10px] text-charcoal/40">
                Send a message to start
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
