"use client";

import { useProgressStages } from "@/lib/stores/assistant-store";
import { CircleNotch, GlobeHemisphereWest, CheckCircle } from "@phosphor-icons/react";
import { AssistantEventData, ToolEvent, ProgressEvent } from "@/lib/types/assistant";

interface ThinkingPanelProps {
  events: AssistantEventData[];
  isStreaming: boolean;
}

export function ThinkingPanel({ events, isStreaming }: ThinkingPanelProps) {
  const progressStages = useProgressStages();
  
  // Extract events from the current turn
  let lastUserIndex = -1;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].type === "message" && (events[i] as any).role === "user") {
      lastUserIndex = i;
      break;
    }
  }
  
  const currentTurnEvents = lastUserIndex >= 0 ? events.slice(lastUserIndex + 1) : events;
  
  // Extract domains from ProgressEvents (e.g. stage="reading", message="Đang đọc nội dung từ https://...")
  // Also from ToolEvents if they have args.url
  const visitedDomains = new Set<string>();
  
  currentTurnEvents.forEach(e => {
    if (e.type === "progress") {
      const pe = e as ProgressEvent;
      const match = pe.message.match(/https?:\/\/([^\/]+)/);
      if (match) visitedDomains.add(match[1]);
    } else if (e.type === "tool") {
      const te = e as ToolEvent;
      if (te.name === "web_search" && te.args?.url) {
         try {
           const url = new URL(te.args.url as string);
           visitedDomains.add(url.hostname);
         } catch(e) {}
      }
    }
  });

  // Active progress message
  const stagesArray = Array.from(progressStages.values());
  const latestProgress = stagesArray.length > 0 ? stagesArray[stagesArray.length - 1] : null;

  // Render logic
  // Show if streaming is true AND there is some progress/tool activity, 
  // OR if streaming is false but we visited domains in this turn
  const hasActivity = visitedDomains.size > 0 || stagesArray.length > 0;
  
  if (!isStreaming && visitedDomains.size === 0) {
    return null;
  }
  
  if (!hasActivity && isStreaming && !latestProgress) {
      // Just waiting for the first progress
      return (
        <div className="mb-4 flex items-center gap-2 text-charcoal font-ui text-sm py-2 animate-fade-in">
          <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
          Initializing research workflow...
        </div>
      );
  }

  return (
    <div className="mb-6 overflow-hidden rounded-2xl border border-charcoal/10 bg-gradient-to-br from-surface-card to-surface-bone/50 shadow-sm animate-fade-in-up">
      <div className="flex items-center gap-3 px-4 py-3 border-b border-charcoal/5 bg-canvas/40">
        {isStreaming ? (
          <CircleNotch size={16} className="text-primary animate-spin" weight="bold" />
        ) : (
          <CheckCircle size={16} className="text-green-500" weight="fill" />
        )}
        <span className="font-ui text-sm font-semibold text-ink">
          {isStreaming 
            ? (latestProgress?.message || "Processing...") 
            : "Research complete"}
        </span>
      </div>
      
      {visitedDomains.size > 0 && (
        <div className="px-4 py-3 bg-surface-card">
          <span className="block font-ui text-[10px] font-bold uppercase tracking-wider text-charcoal/50 mb-2">
            Sources visited
          </span>
          <div className="flex flex-wrap gap-2">
            {Array.from(visitedDomains).map(domain => (
              <span key={domain} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-bone border border-charcoal/10 font-mono text-[11px] text-charcoal transition-colors hover:bg-charcoal/5">
                <GlobeHemisphereWest size={12} className="text-primary/60" />
                {domain}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
