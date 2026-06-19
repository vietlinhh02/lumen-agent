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

import { useCurrentIteration, useLastToolUsed } from "@/lib/stores/assistant-store";
import {
  Brain,
  Gear,
  Lightning,
} from "@phosphor-icons/react";

interface IterationPanelProps {
  /** Optional title for the panel */
  title?: string;
}

export function IterationPanel({ title = "Agent Progress" }: IterationPanelProps) {
  const { iteration, max, phase } = useCurrentIteration();
  const lastToolUsed = useLastToolUsed();

  // Calculate progress
  const progressPercent = max > 0 ? ((iteration + 1) / max) * 100 : 0;
  const hasProgress = iteration > 0 || phase !== null;

  return (
    <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-surface-bone/50 border border-charcoal/5">
      {/* Status Icon */}
      <div className="flex-shrink-0 flex items-center justify-center">
        {phase === "reasoning" ? (
          <Brain size={12} className="text-primary animate-pulse" weight="fill" />
        ) : phase === "acting" ? (
          <Gear size={12} className="text-green-600 animate-spin" weight="fill" style={{ animationDuration: "2s" }} />
        ) : (
          <Lightning size={12} className="text-charcoal/40" weight="fill" />
        )}
      </div>

      {/* Status Text */}
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="font-ui text-[10px] font-medium text-ink truncate whitespace-nowrap">
          {phase === null && "Idle"}
          {phase === "reasoning" && "Analyzing…"}
          {phase === "acting" && "Executing"}
        </span>
        {lastToolUsed && phase === "acting" && (
          <span className="font-mono text-[9px] text-charcoal bg-canvas px-1 rounded truncate max-w-[80px]">
            {lastToolUsed}
          </span>
        )}
      </div>
      
      {/* Iteration Count */}
      {hasProgress && (
        <>
          <div className="h-2.5 w-[1px] bg-charcoal/20" />
          <span className="font-ui text-[9px] font-medium text-charcoal whitespace-nowrap">
            {Math.max(1, iteration + 1)}/{max}
          </span>
        </>
      )}
    </div>
  );
}
