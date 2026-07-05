/**
 * ConfirmProjectPanel - Shows the extracted project details and asks user to confirm
 * before starting the Deep Research pipeline.
 *
 * Handles the ActionEvent(type="action", action_type="confirm_project") from backend.
 */

"use client";

import { useAssistantStore } from "@/lib/stores/assistant-store";
import { Globe, CheckCircle, X, BookOpen, Question } from "@phosphor-icons/react";

export function ConfirmProjectPanel() {
  const pendingAction = useAssistantStore((s) => s._pendingAction);
  const confirmDeepResearch = useAssistantStore((s) => s.confirmDeepResearch);
  const cancelDeepResearch = useAssistantStore((s) => s.cancelDeepResearch);
  const initialResearchMessage = useAssistantStore((s) => s._initialResearchMessage);
  const messages = useAssistantStore((s) => s.messagesBySession);
  const activeSessionId = useAssistantStore((s) => s.activeSessionId);

  if (!pendingAction || pendingAction.action_type !== "confirm_project") return null;

  const data = pendingAction.data as {
    title?: string;
    topic?: string;
    research_question?: string;
  };

  // Get the original user query from the last user message
  const sessionMessages = activeSessionId ? (messages.get(activeSessionId) ?? []) : [];
  const lastUserMsg = [...sessionMessages].reverse().find((m) => m.role === "user");
  const originalMessage = initialResearchMessage || lastUserMsg?.content || "";

  return (
    <div className="my-4 mx-auto max-w-lg animate-fade-in-up">
      <div className="overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-surface-card to-primary/5 shadow-lg">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-primary/10 bg-primary/5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Globe size={22} className="text-primary" weight="fill" />
          </div>
          <div className="min-w-0">
            <h3 className="font-ui text-sm font-semibold text-ink">
              Deep Research Ready
            </h3>
            <p className="font-ui text-xs text-charcoal/70">
              Review the project details before starting
            </p>
          </div>
        </div>

        {/* Project details */}
        <div className="px-5 py-4 space-y-3 bg-surface-card">
          <div className="flex items-start gap-3">
            <BookOpen size={16} className="text-primary mt-0.5 shrink-0" weight="duotone" />
            <div className="min-w-0">
              <p className="font-ui text-[11px] font-bold uppercase tracking-wider text-charcoal/50 mb-0.5">
                Title
              </p>
              <p className="font-ui text-sm text-ink">
                {data.title || "Research Project"}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <Globe size={16} className="text-primary mt-0.5 shrink-0" weight="duotone" />
            <div className="min-w-0">
              <p className="font-ui text-[11px] font-bold uppercase tracking-wider text-charcoal/50 mb-0.5">
                Topic
              </p>
              <p className="font-ui text-sm text-ink">
                {data.topic || "Not specified"}
              </p>
            </div>
          </div>

          {data.research_question && (
            <div className="flex items-start gap-3">
              <Question size={16} className="text-primary mt-0.5 shrink-0" weight="duotone" />
              <div className="min-w-0">
                <p className="font-ui text-[11px] font-bold uppercase tracking-wider text-charcoal/50 mb-0.5">
                  Research Question
                </p>
                <p className="font-ui text-sm text-ink">
                  {data.research_question}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 px-5 py-4 border-t border-hairline bg-canvas/50">
          <button
            type="button"
            onClick={cancelDeepResearch}
            className="flex items-center gap-2 rounded-xl border border-charcoal/20 px-4 py-2.5 font-ui text-sm font-medium text-charcoal hover:bg-surface-bone transition-colors"
          >
            <X size={16} />
            Cancel
          </button>
          <div className="relative flex-1 group cursor-not-allowed">
            <button
              type="button"
              disabled={true}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-primary/40 px-4 py-2.5 font-ui text-sm font-semibold text-white/50 pointer-events-none"
            >
              <CheckCircle size={18} weight="fill" />
              Begin Deep Research
            </button>
            <div className="absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 scale-95 opacity-0 transition-all duration-200 pointer-events-none group-hover:scale-100 group-hover:opacity-100 whitespace-nowrap rounded-lg bg-charcoal px-2.5 py-1 text-[10px] font-medium text-white shadow-md border border-charcoal/20">
              Feature in development
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-charcoal" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
