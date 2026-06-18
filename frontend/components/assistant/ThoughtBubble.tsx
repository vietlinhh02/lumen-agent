/**
 * ThoughtBubble - Displays the ReAct agent's streaming chain-of-thought.
 * 
 * Shows:
 * - Collapsible card with italic gray text
 * - "Thinking… (iteration N/max)" header
 * - Auto-expands while streaming, collapses on next user message
 */

"use client";

import { useState } from "react";
import { useCurrentIteration, useCurrentThought, useIsStreaming } from "@/lib/stores/assistant-store";
import { Brain, CaretDown, CaretUp, Sparkle } from "@phosphor-icons/react";

interface ThoughtBubbleProps {
  /** Current iteration being displayed */
  iteration: number;
  /** Custom content override for historical thoughts */
  content?: string;
  /** Custom streaming status override for historical thoughts */
  isStreamingOverride?: boolean;
}

export function ThoughtBubble({ iteration, content, isStreamingOverride }: ThoughtBubbleProps) {
  const { max, phase } = useCurrentIteration();
  const storeThought = useCurrentThought();
  const storeIsStreaming = useIsStreaming();

  const thought = content !== undefined ? content : storeThought;
  const isStreaming = isStreamingOverride !== undefined ? isStreamingOverride : storeIsStreaming;
  const [isExpanded, setIsExpanded] = useState(true);

  // Don't render if no thought content
  if (!thought.trim()) {
    return null;
  }

  return (
    <div className="animate-fade-in-up overflow-hidden rounded-2xl border border-charcoal/10 bg-gradient-to-br from-surface-card to-surface-bone/50 shadow-sm">
      {/* Header - always visible */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between px-4 py-2.5 hover:bg-surface-bone/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${
            phase === "reasoning" 
              ? "bg-primary/10 text-primary" 
              : "bg-green-500/10 text-green-600"
          }`}>
            {phase === "reasoning" ? (
              <Brain size={14} weight="fill" className={isStreaming ? "animate-pulse" : ""} />
            ) : (
              <Sparkle size={14} weight="fill" />
            )}
          </div>
          <div className="text-left">
            <p className="font-ui text-xs font-medium text-ink">
              {phase === "reasoning" ? "Thinking…" : "Acting…"}
            </p>
            <p className="font-ui text-[10px] text-charcoal/60">
              Iteration {iteration + 1}/{max}
            </p>
          </div>
        </div>

        {isExpanded ? (
          <CaretUp size={14} className="text-charcoal/60" />
        ) : (
          <CaretDown size={14} className="text-charcoal/60" />
        )}
      </button>

      {/* Thought content */}
      {isExpanded && (
        <div className="px-4 pb-3">
          <div 
            className="rounded-lg bg-canvas/80 px-3 py-2 font-mono text-xs leading-relaxed text-charcoal italic"
            style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
          >
            {thought}
            {isStreaming && (
              <span className="inline-block h-3 w-0.5 animate-pulse bg-charcoal/40 ml-1 align-middle" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Compact thought indicator for inline display during streaming.
 */
export function ThoughtIndicator() {
  const isStreaming = useIsStreaming();
  const { iteration, max, phase } = useCurrentIteration();
  const thought = useCurrentThought();
  const [isExpanded, setIsExpanded] = useState(false);

  if (!isStreaming) return null;

  return (
    <div className="relative">
      {/* Mini indicator */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 rounded-full bg-surface-bone/80 px-3 py-1.5 font-ui text-xs text-charcoal hover:bg-surface-bone transition-colors"
      >
        <Brain size={12} className="text-primary animate-pulse" />
        <span>
          {phase === "reasoning" ? "Thinking" : "Acting"} · {iteration + 1}/{max}
        </span>
      </button>

      {/* Expanded tooltip */}
      {isExpanded && thought && (
        <div className="absolute left-0 top-full z-20 mt-2 w-80 rounded-xl border border-charcoal/20 bg-canvas p-3 shadow-lg">
          <p className="mb-2 font-ui text-[10px] font-semibold uppercase tracking-wider text-charcoal/50">
            Chain of Thought
          </p>
          <p className="font-mono text-xs leading-relaxed text-charcoal/80 italic">
            {thought.slice(-200)}
            {thought.length > 200 && "..."}
          </p>
        </div>
      )}
    </div>
  );
}

export interface GroupedThought {
  id: string;
  iteration: number;
  content: string;
  isStreaming: boolean;
}

interface GroupedThoughtsProps {
  thoughts: GroupedThought[];
  isStreaming: boolean;
}

export function GroupedThoughts({ thoughts, isStreaming }: GroupedThoughtsProps) {
  // If the last thought is streaming, expand by default; otherwise collapse by default to avoid clutter
  const hasStreaming = thoughts.some((t) => t.isStreaming);
  const [isExpanded, setIsExpanded] = useState(hasStreaming);

  if (thoughts.length === 0) return null;

  return (
    <div className="animate-fade-in-up overflow-hidden rounded-2xl border border-charcoal/10 bg-gradient-to-br from-surface-card to-surface-bone/50 shadow-sm">
      {/* Header - collapsible */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between px-4 py-2.5 hover:bg-surface-bone/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Brain size={14} weight="fill" className={isStreaming ? "animate-pulse" : ""} />
          </div>
          <div className="text-left">
            <p className="font-ui text-xs font-semibold text-ink">
              Agent Thinking & Actions
            </p>
            <p className="font-ui text-[10px] text-charcoal/60">
              {thoughts.length} step{thoughts.length > 1 ? "s" : ""}
            </p>
          </div>
        </div>

        {isExpanded ? (
          <CaretUp size={14} className="text-charcoal/60" />
        ) : (
          <CaretDown size={14} className="text-charcoal/60" />
        )}
      </button>

      {/* Expanded thoughts list */}
      {isExpanded && (
        <div className="px-4 pb-3 space-y-3">
          {thoughts.map((t, index) => (
            <div key={t.id || index} className="space-y-1.5 border-t border-charcoal/5 pt-2.5 first:border-0 first:pt-0">
              <div className="flex items-center gap-2">
                <span className="font-ui text-[10px] font-bold uppercase tracking-wider text-charcoal/40">
                  Step {t.iteration + 1}
                </span>
              </div>
              <div 
                className="rounded-lg bg-canvas/80 px-3 py-2 font-mono text-xs leading-relaxed text-charcoal italic"
                style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
              >
                {t.content}
                {t.isStreaming && (
                  <span className="inline-block h-3 w-0.5 animate-pulse bg-charcoal/40 ml-1 align-middle" />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
