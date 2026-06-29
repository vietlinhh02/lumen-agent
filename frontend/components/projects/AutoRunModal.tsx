"use client";

import { useEffect, useState, useRef } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { CircleNotch, CheckCircle, Warning, X, MagicWand, Graph, MagnifyingGlass, Lightbulb, PencilLine } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useProjectsStore } from "@/lib/stores/projects-store";

interface AutoRunModalProps {
  projectId: string;
  topic: string;
  researchQuestion?: string | null;
  isOpen: boolean;
  onClose: () => void;
}

interface Step {
  id: string;
  label: string;
  icon: typeof MagicWand;
  status: "idle" | "running" | "done" | "error";
  details?: string;
}

const STEPS: Step[] = [
  { id: "query_planner", label: "Planning Research Query", icon: MagicWand, status: "idle" },
  { id: "search_agent", label: "Searching Academic Literature", icon: MagnifyingGlass, status: "idle" },
  { id: "matrix_extraction", label: "Extracting Knowledge Matrix", icon: Graph, status: "idle" },
  { id: "gap_analysis", label: "Analyzing Research Gaps", icon: Lightbulb, status: "idle" },
  { id: "review_writer", label: "Writing Literature Review", icon: PencilLine, status: "idle" },
  { id: "citation_validator", label: "Validating Citations", icon: CheckCircle, status: "idle" },
];

export function AutoRunModal({ projectId, topic, researchQuestion, isOpen, onClose }: AutoRunModalProps) {
  const [steps, setSteps] = useState<Step[]>(STEPS);
  const [isFinished, setIsFinished] = useState(false);
  const [isError, setIsError] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  
  const refreshProjects = useProjectsStore((s) => s.fetchProjects);

  // Auto-start when modal opens
  useEffect(() => {
    let abortController = abortControllerRef.current;
    
    const initializeState = () => {
      setIsFinished(false);
      setIsError(false);
      // Mark first step as running immediately to feel responsive
      setSteps(STEPS.map((s, i) => i === 0 ? { ...s, status: "running" } : { ...s, status: "idle", details: "" }));
    };

    if (isOpen) {
      if (abortController) {
        abortController.abort();
      }
      abortController = new AbortController();
      abortControllerRef.current = abortController;
      
      initializeState();

      const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL 
        ? `${process.env.NEXT_PUBLIC_BACKEND_URL}/api`
        : "/api";

      fetchEventSource(`${BASE_URL}/agents/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "text/event-stream",
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
              const nodeName = parsed.node;
              const state = parsed.state;
              
              setSteps(prev => {
                const newSteps = [...prev];
                
                // If we got a node update, mark all previous as done, current as running
                let foundCurrent = false;
                for (let i = 0; i < newSteps.length; i++) {
                  // We map some node names together since search has subnodes like save_screened
                  const matchesNode = 
                    newSteps[i].id === nodeName || 
                    (newSteps[i].id === "search_agent" && ["language_bias", "save_screened"].includes(nodeName)) ||
                    (newSteps[i].id === "gap_analysis" && nodeName === "conflict_detection");

                  if (matchesNode) {
                    newSteps[i].status = "running";
                    // Update details with state
                    if (nodeName === "save_screened") newSteps[i].details = `Found ${state.papers_found || 0} papers`;
                    if (nodeName === "matrix_extraction") newSteps[i].details = `Extracted ${state.matrix_rows || 0} rows`;
                    if (nodeName === "gap_analysis") newSteps[i].details = `Detected ${state.gaps_count || 0} gaps`;
                    if (nodeName === "review_writer") newSteps[i].details = `Generated ${state.report_sections || 0} sections`;
                    foundCurrent = true;
                  } else if (!foundCurrent) {
                    newSteps[i].status = "done";
                  } else {
                    newSteps[i].status = "idle";
                  }
                }
                
                return newSteps;
              });
            } catch (err) {
              console.error("Error parsing update", err);
            }
          } else if (msg.event === "complete") {
            setSteps(prev => prev.map(s => ({ ...s, status: "done" })));
            setIsFinished(true);
            refreshProjects();
            toast.success("Automated research completed successfully!");
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
              newSteps[runningIdx].status = "error";
              newSteps[runningIdx].details = "Process failed";
            }
            return newSteps;
          });
          toast.error("Pipeline encountered an error.");
          throw err; // Stop retrying
        },
      }).catch(error => {
        console.error("Fetch event source error", error);
        setIsError(true);
      });
    } else {
      // Cleanup on close
      if (abortController) {
        abortController.abort();
      }
    }
    
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, projectId, topic, researchQuestion]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-ink/30 backdrop-blur-sm transition-opacity" 
        onClick={() => !isFinished && !isError ? null : onClose()} 
      />
      
      {/* Modal */}
      <div className="relative w-full max-w-lg overflow-hidden rounded-[20px] bg-surface p-6 shadow-xl animate-in fade-in zoom-in-95 duration-200">
        <button 
          onClick={onClose}
          className="absolute right-4 top-4 rounded-full p-1.5 text-ash hover:bg-surface-bone hover:text-ink transition-colors focus-ring"
        >
          <X size={18} weight="bold" />
        </button>

        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <MagicWand size={22} weight="fill" />
          </div>
          <div>
            <h2 className="font-ui text-lg font-bold text-ink leading-tight">Auto-Pilot Agent</h2>
            <p className="font-ui text-sm text-ash">Running the complete research workflow autonomously</p>
          </div>
        </div>

        {/* Steps Tracker */}
        <div className="space-y-4 rounded-[16px] bg-surface-card p-5 border border-hairline relative overflow-hidden">
          {/* Subtle animated background gradient when running */}
          {!isFinished && !isError && (
             <div className="absolute inset-0 opacity-[0.03] bg-gradient-to-r from-primary via-purple-500 to-primary animate-pulse" />
          )}

          {steps.map((step, idx) => (
            <div key={step.id} className="relative z-10 flex gap-4">
              {/* Timeline line */}
              {idx < steps.length - 1 && (
                <div className={`absolute left-3.5 top-8 w-[2px] h-full -ml-[1px] ${
                  step.status === "done" ? "bg-primary/50" : "bg-hairline"
                }`} />
              )}
              
              {/* Step Icon */}
              <div className="relative mt-0.5 shrink-0">
                <div className={`flex h-7 w-7 items-center justify-center rounded-full border-2 bg-surface transition-colors duration-300 ${
                  step.status === "done" ? "border-primary text-primary" :
                  step.status === "running" ? "border-primary text-primary" :
                  step.status === "error" ? "border-red-500 text-red-500" :
                  "border-ash/30 text-ash"
                }`}>
                  {step.status === "done" ? (
                    <CheckCircle size={14} weight="fill" />
                  ) : step.status === "error" ? (
                    <Warning size={14} weight="fill" />
                  ) : step.status === "running" ? (
                    <CircleNotch size={14} weight="bold" className="animate-spin" />
                  ) : (
                    <span className="font-ui text-[10px] font-bold">{idx + 1}</span>
                  )}
                </div>
              </div>

              {/* Step Content */}
              <div className="flex flex-col pb-2 pt-0.5">
                <div className={`font-ui text-[14px] font-semibold transition-colors duration-300 ${
                  step.status === "idle" ? "text-ash" :
                  step.status === "error" ? "text-red-600" :
                  "text-ink"
                }`}>
                  {step.label}
                </div>
                {step.details && (
                  <div className="font-ui text-[12px] text-stone mt-0.5">
                    {step.details}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Footer actions */}
        <div className="mt-6 flex justify-end gap-3">
          {(isFinished || isError) ? (
            <button
              onClick={onClose}
              className="focus-ring h-10 rounded-full bg-primary px-6 font-ui text-[14px] font-semibold text-on-primary hover:bg-primary-deep"
            >
              Close
            </button>
          ) : (
            <button
              onClick={() => {
                if (abortControllerRef.current) abortControllerRef.current.abort();
                onClose();
              }}
              className="focus-ring h-10 rounded-full bg-surface-bone px-5 font-ui text-[14px] font-semibold text-ink hover:bg-hairline"
            >
              Cancel Process
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
