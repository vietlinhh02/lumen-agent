"use client";

import { useEffect, useState, useRef } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import {
  CircleNotch,
  CheckCircle,
  Warning,
  X,
  MagicWand,
  Graph,
  MagnifyingGlass,
  Lightbulb,
  PencilLine,
  CheckFat,
  ArrowRight,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { TOKEN_KEY } from "@/lib/jwt";

interface AutoRunModalProps {
  projectId: string;
  topic: string;
  researchQuestion?: string | null;
  isOpen: boolean;
  onClose: () => void;
}

type StepStatus = "idle" | "running" | "done" | "error";

interface Step {
  id: string;
  label: string;
  description: string;
  icon: typeof MagicWand;
  status: StepStatus;
  details?: string;
}

const INITIAL_STEPS: Step[] = [
  {
    id: "query_planner",
    label: "Query Planning",
    description: "Analysing your research topic and building structured search queries.",
    icon: MagicWand,
    status: "idle",
  },
  {
    id: "search_agent",
    label: "Literature Search",
    description: "Searching academic databases and screening papers for relevance.",
    icon: MagnifyingGlass,
    status: "idle",
  },
  {
    id: "matrix_extraction",
    label: "Knowledge Matrix",
    description: "Extracting key data points across all papers into a structured matrix.",
    icon: Graph,
    status: "idle",
  },
  {
    id: "gap_analysis",
    label: "Gap Analysis",
    description: "Detecting research gaps and conflicts across the literature corpus.",
    icon: Lightbulb,
    status: "idle",
  },
  {
    id: "review_writer",
    label: "Literature Review",
    description: "Writing a comprehensive, citation-safe literature review.",
    icon: PencilLine,
    status: "idle",
  },
  {
    id: "citation_validator",
    label: "Citation Validation",
    description: "Verifying all citations are accurate and properly attributed.",
    icon: CheckFat,
    status: "idle",
  },
];

/** Maps LangGraph node names → our step IDs */
function resolveStepId(nodeName: string): string | null {
  if (nodeName === "query_planner") return "query_planner";
  if (["search_agent", "language_bias", "save_screened"].includes(nodeName)) return "search_agent";
  if (nodeName === "matrix_extraction") return "matrix_extraction";
  if (["gap_analysis", "conflict_detection"].includes(nodeName)) return "gap_analysis";
  if (nodeName === "review_writer") return "review_writer";
  if (nodeName === "citation_validator") return "citation_validator";
  return null;
}

export function AutoRunModal({ projectId, topic, researchQuestion, isOpen, onClose }: AutoRunModalProps) {
  const [steps, setSteps] = useState<Step[]>(INITIAL_STEPS);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [isFinished, setIsFinished] = useState(false);
  const [isError, setIsError] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const refreshProjects = useProjectsStore((s) => s.fetchProjects);

  useEffect(() => {
    let abortController = abortControllerRef.current;

    const initializeState = () => {
      setSteps(INITIAL_STEPS.map((s, i) => ({
        ...s,
        status: i === 0 ? "running" : "idle",
        details: "",
      })));
      setCurrentIdx(0);
      setIsFinished(false);
      setIsError(false);
    };

    if (isOpen) {
      if (abortController) abortController.abort();
      abortController = new AbortController();
      abortControllerRef.current = abortController;
      initializeState();

      const token = localStorage.getItem(TOKEN_KEY);
      const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL
        ? `${process.env.NEXT_PUBLIC_BACKEND_URL}/api`
        : "/api";

      fetchEventSource(`${BASE_URL}/agents/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          project_id: projectId,
          topic,
          research_question: researchQuestion || "",
        }),
        signal: abortController.signal,
        onmessage(msg) {
          if (msg.event === "update") {
            try {
              const parsed = JSON.parse(msg.data);
              const nodeName: string = parsed.node;
              const state = parsed.state;
              const stepId = resolveStepId(nodeName);
              if (!stepId) return;

              setSteps(prev => {
                const stepIdx = prev.findIndex(s => s.id === stepId);
                if (stepIdx === -1) return prev;

                setCurrentIdx(stepIdx);

                return prev.map((s, i) => {
                  if (i < stepIdx) return { ...s, status: "done" };
                  if (i === stepIdx) {
                    let details = s.details;
                    if (nodeName === "save_screened") details = `Found ${state.papers_found || 0} papers`;
                    if (nodeName === "matrix_extraction") details = `Extracted ${state.matrix_rows || 0} rows`;
                    if (nodeName === "gap_analysis") details = `Detected ${state.gaps_count || 0} gaps`;
                    if (nodeName === "review_writer") details = `Generated ${state.report_sections || 0} sections`;
                    return { ...s, status: "running", details };
                  }
                  return { ...s, status: "idle" };
                });
              });
            } catch (err) {
              console.error("Error parsing update", err);
            }
          } else if (msg.event === "complete") {
            setSteps(prev => prev.map(s => ({ ...s, status: "done" })));
            setCurrentIdx(INITIAL_STEPS.length - 1);
            setIsFinished(true);
            refreshProjects();
            toast.success("Research pipeline completed!");
          } else if (msg.event === "error") {
            throw new Error(msg.data);
          }
        },
        onerror(err) {
          console.error("Stream error", err);
          setIsError(true);
          setSteps(prev => {
            const newSteps = [...prev];
            const runningIdx = newSteps.findIndex(s => s.status === "running");
            if (runningIdx !== -1) {
              newSteps[runningIdx] = {
                ...newSteps[runningIdx],
                status: "error",
                details: "Step failed",
              };
            }
            return newSteps;
          });
          toast.error("Pipeline encountered an error.");
          throw err;
        },
      }).catch(error => {
        if ((error as Error)?.name !== "AbortError") {
          console.error("Fetch event source error", error);
          setIsError(true);
        }
      });
    } else {
      if (abortController) abortController.abort();
    }

    return () => {
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, projectId, topic, researchQuestion]);

  if (!isOpen) return null;

  const current = steps[currentIdx];
  const Icon = current.icon;
  const doneCount = steps.filter(s => s.status === "done").length;
  const progressPct = isFinished ? 100 : Math.round((doneCount / steps.length) * 100);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-md" />

      {/* Modal — full-screen feel on mobile, centered card on desktop */}
      <div className="relative flex w-full max-w-xl flex-col overflow-hidden rounded-[24px] bg-surface shadow-2xl">

        {/* Top close */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 z-10 rounded-full p-2 text-ash hover:bg-surface-bone hover:text-ink transition-colors focus-ring"
        >
          <X size={18} weight="bold" />
        </button>

        {/* ── HERO AREA ── */}
        <div className={`relative flex flex-col items-center justify-center px-8 pb-8 pt-12 text-center transition-colors duration-700 ${
          isError ? "bg-red-50 dark:bg-red-950/20" : "bg-gradient-to-b from-primary/8 to-surface"
        }`}>
          {/* Animated ring */}
          <div className="relative mb-5">
            <div className={`absolute inset-0 rounded-full blur-xl opacity-40 transition-all duration-700 ${
              isError ? "bg-red-400" : isFinished ? "bg-emerald-400" : "bg-primary animate-pulse"
            }`} />
            <div className={`relative flex h-20 w-20 items-center justify-center rounded-full border-2 transition-all duration-700 ${
              isError
                ? "border-red-400 bg-red-50 text-red-500"
                : isFinished
                  ? "border-emerald-400 bg-emerald-50 text-emerald-600"
                  : "border-primary/40 bg-primary/10 text-primary"
            }`}>
              {isFinished ? (
                <CheckCircle size={40} weight="fill" />
              ) : isError ? (
                <Warning size={40} weight="fill" />
              ) : current.status === "running" ? (
                <CircleNotch size={40} weight="bold" className="animate-spin" />
              ) : (
                <Icon size={40} weight="fill" />
              )}
            </div>
          </div>

          {/* Step label */}
          <div className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-ash mb-1">
            {isFinished ? "Complete" : isError ? "Error" : `Step ${currentIdx + 1} of ${steps.length}`}
          </div>
          <h2 className="font-ui text-[22px] font-bold text-ink leading-tight">
            {isFinished
              ? "All done!"
              : isError
                ? "Something went wrong"
                : current.label}
          </h2>
          <p className="mt-2 font-ui text-[14px] text-ash max-w-xs leading-relaxed">
            {isFinished
              ? "Your full research pipeline completed successfully. Your report is ready."
              : isError
                ? "The pipeline encountered an unexpected error. Check the console for details."
                : current.description}
          </p>
          {current.details && !isFinished && (
            <div className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 font-ui text-[12px] font-medium text-primary">
              {current.details}
            </div>
          )}
        </div>

        {/* ── PROGRESS BAR ── */}
        <div className="h-1 w-full bg-surface-bone">
          <div
            className={`h-full transition-all duration-700 ease-out ${isError ? "bg-red-400" : isFinished ? "bg-emerald-500" : "bg-primary"}`}
            style={{ width: `${progressPct}%` }}
          />
        </div>

        {/* ── STEP TRACK ── */}
        <div className="px-6 py-4 flex items-center gap-2 overflow-x-auto scrollbar-none">
          {steps.map((step, idx) => {
            const StepIcon = step.icon;
            const isActive = idx === currentIdx && !isFinished;
            return (
              <div key={step.id} className="flex items-center gap-2 shrink-0">
                <div className={`flex h-7 w-7 items-center justify-center rounded-full border-2 transition-all duration-300 ${
                  step.status === "done"
                    ? "border-primary bg-primary text-on-primary"
                    : step.status === "error"
                      ? "border-red-400 bg-red-50 text-red-500"
                      : isActive
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-ash/20 bg-surface-bone text-ash"
                }`}>
                  {step.status === "done" ? (
                    <CheckCircle size={13} weight="fill" />
                  ) : step.status === "running" ? (
                    <CircleNotch size={13} weight="bold" className="animate-spin" />
                  ) : step.status === "error" ? (
                    <Warning size={13} weight="fill" />
                  ) : (
                    <StepIcon size={12} weight="fill" />
                  )}
                </div>
                {/* connector line */}
                {idx < steps.length - 1 && (
                  <div className={`h-[2px] w-5 rounded-full transition-colors duration-500 ${
                    step.status === "done" ? "bg-primary/50" : "bg-hairline"
                  }`} />
                )}
              </div>
            );
          })}
        </div>

        {/* ── FOOTER ── */}
        <div className="flex items-center justify-between border-t border-hairline px-6 py-4">
          <span className="font-ui text-[12px] text-ash">
            {isFinished
              ? "✓ Pipeline complete"
              : isError
                ? "✗ Pipeline stopped"
                : `Running ${steps.filter(s => s.status === "done").length + (steps.some(s => s.status === "running") ? 1 : 0)} / ${steps.length}`}
          </span>
          <div className="flex gap-2">
            {!isFinished && !isError ? (
              <button
                onClick={() => {
                  if (abortControllerRef.current) abortControllerRef.current.abort();
                  onClose();
                }}
                className="focus-ring h-9 rounded-full bg-surface-bone px-5 font-ui text-[13px] font-semibold text-ink hover:bg-hairline transition-colors"
              >
                Cancel
              </button>
            ) : (
              <button
                onClick={onClose}
                className="focus-ring inline-flex h-9 items-center gap-2 rounded-full bg-primary px-5 font-ui text-[13px] font-semibold text-on-primary hover:bg-primary-deep transition-colors"
              >
                {isFinished ? "View Results" : "Close"}
                {isFinished && <ArrowRight size={13} weight="bold" />}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
