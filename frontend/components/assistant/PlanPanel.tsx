/**
 * PlanPanel - Sticky plan view with step statuses.
 * 
 * Shows the current plan with all steps and their status:
 * - pending: not started yet
 * - running: currently executing
 * - completed: successfully finished
 * - failed: error occurred
 */

"use client";

import type { PlanData } from "@/lib/types/assistant";
import {
  CheckCircle,
  XCircle,
  Circle,
  Spinner,
  CaretDown,
  CaretUp,
} from "@phosphor-icons/react";
import { useState } from "react";

interface PlanPanelProps {
  plan: PlanData;
}

const stepStatusConfig = {
  pending: {
    icon: <Circle size={14} className="text-charcoal/40" />,
    label: "Pending",
    color: "text-charcoal/60",
    bg: "bg-charcoal/5",
  },
  running: {
    icon: <Spinner size={14} className="text-primary animate-spin" />,
    label: "Running",
    color: "text-primary",
    bg: "bg-primary/5",
  },
  completed: {
    icon: <CheckCircle size={14} className="text-green-500" weight="fill" />,
    label: "Done",
    color: "text-green-600",
    bg: "bg-green-50",
  },
  failed: {
    icon: <XCircle size={14} className="text-red-500" weight="fill" />,
    label: "Failed",
    color: "text-red-500",
    bg: "bg-red-50",
  },
};

export function PlanPanel({ plan }: PlanPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  // Calculate progress
  const completedSteps = plan.steps.filter((s) => s.status === "completed").length;
  const totalSteps = plan.steps.length;
  const progressPercent = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0;

  // Find running step
  const runningStep = plan.steps.find((s) => s.status === "running");

  return (
    <div className="rounded-xl border border-charcoal/20 bg-surface-card overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between px-4 py-3 hover:bg-surface-bone/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              className="text-primary"
            >
              <path
                d="M2 4h12M2 8h8M2 12h10"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div className="text-left">
            <p className="font-ui text-sm font-medium text-ink">
              {plan.title || "Research Plan"}
            </p>
            <p className="font-ui text-xs text-charcoal">
              {completedSteps}/{totalSteps} steps completed
              {runningStep && ` • ${runningStep.description}`}
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
      <div className="h-1 bg-charcoal/10">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Steps */}
      {isExpanded && (
        <div className="p-3 pt-2">
          <div className="space-y-2">
            {plan.steps.map((step, index) => {
              const config = stepStatusConfig[step.status];
              return (
                <div
                  key={step.id}
                  className={`flex items-center gap-3 rounded-lg p-2 ${config.bg} transition-colors`}
                >
                  {/* Step number */}
                  <span
                    className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-medium ${
                      step.status === "completed"
                        ? "bg-green-500 text-white"
                        : step.status === "failed"
                        ? "bg-red-500 text-white"
                        : step.status === "running"
                        ? "bg-primary text-white"
                        : "bg-charcoal/20 text-charcoal"
                    }`}
                  >
                    {index + 1}
                  </span>

                  {/* Status icon */}
                  <div className="flex-shrink-0">{config.icon}</div>

                  {/* Description */}
                  <p className={`flex-1 font-ui text-xs ${config.color}`}>
                    {step.description}
                  </p>

                  {/* Expected tool badge */}
                  <span className="rounded bg-canvas px-1.5 py-0.5 font-mono text-[10px] text-charcoal/70">
                    {step.expected_tool}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
