/* eslint-disable */
/**
 * ChatMessage - Renders a single message/event in the chat stream.
 * 
 * Handles all event types:
 * - message: text bubble (user or assistant)
 * - thought: streaming reasoning (renders ThoughtBubble)
 * - iteration: agent loop progress (handled silently)
 * - error: error message
 */

"use client";

import { useState } from "react";
import Image from "next/image";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeTwemojify from "@yuna0x0/rehype-twemojify";
import type {
  AssistantEventData,
  MessageEvent,
} from "@/lib/types/assistant";
import { ThoughtBubble } from "./ThoughtBubble";
import { IterationPanel } from "./IterationPanel";
import { Brain, CaretDown, CaretUp, ArrowSquareOut } from "@phosphor-icons/react";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { useUIStore } from "@/lib/stores/ui-store";

interface ChatMessageProps {
  event: AssistantEventData;
  userName: string;
  allEvents?: AssistantEventData[];
  /** Whether this message is currently streaming (for assistant messages) */
  isStreaming?: boolean;
  isLastAssistantMessage?: boolean;
}

export function ChatMessage({ event, userName, allEvents, isStreaming, isLastAssistantMessage }: ChatMessageProps) {
  // Handle message events
  if (event.type === "message") {
    return <MessageBubble event={event as MessageEvent} userName={userName} allEvents={allEvents} isStreaming={isStreaming} isLastAssistantMessage={isLastAssistantMessage} />;
  }
  
  // Handle thought events - render ThoughtBubble with turn-specific text
  if (event.type === "thought") {
    const isLastEvent = allEvents ? allEvents[allEvents.length - 1].id === event.id : false;
    // For single ThoughtBubble mode we just want the delta passed into the buffer
    // and rely on store ThoughtBuffer for the current streaming iteration
    // The previous component relied on this text being accumulated, but we can just pass delta since the store clears buffers
    const content = (event as any).delta;
    return (
      <ThoughtBubble
        iteration={event.iteration}
        content={content}
        isStreamingOverride={isLastEvent}
      />
    );
  }
  
  // Handle iteration events - no render, just store update
  // (these are handled by IterationPanel)
  if (event.type === "iteration") {
    return null;
  }
  
  return null;
}

/* ── Helper: Parse ReAct Thought & Action ───────────────────────────────────── */

function parseAssistantMessage(content: string) {
  // Some reasoning models (e.g. MiniMax-M2.7) emit a `` block at the
  // start of their reply instead of the legacy "Thought:" / "Action:" /
  // "Observation:" markers. We must strip it BEFORE handing the rest to
  // ReactMarkdown, otherwise the unknown `` tag is parsed as raw HTML
  // (rehypeRaw is enabled) and React logs "The tag  is unrecognized".
  const thinkRegex = /<think(?:ing)?>([\s\S]*?)<\/think(?:ing)?>/gi;
  const thinkMatches = [...content.matchAll(thinkRegex)];
  const thinkText = thinkMatches
    .map((m) => m[1].trim())
    .filter(Boolean)
    .join("\n\n");

  // Also strip any leftover `` opener/closer that wasn't paired
  // (streaming cut-offs, malformed model output, etc.) so they never
  // leak into the rendered markdown.
  const strippedContent = content
    .replace(thinkRegex, "")
    .replace(/<\/?think(?:ing)?>/gi, "")
    .trim();

  const thoughtRegex = /(?:^|\n)\s*Thought:\s*([\s\S]*?)(?=(?:\n\s*Action:|\n\s*Observation:|$))/i;
  const actionRegex = /(?:^|\n)\s*Action:\s*([\s\S]*?)(?=(?:\n\s*Observation:|$))/i;
  const observationRegex = /(?:^|\n)\s*Observation:\s*([\s\S]*?)$/i;

  const thoughtMatch = strippedContent.match(thoughtRegex);
  const actionMatch = strippedContent.match(actionRegex);
  const observationMatch = strippedContent.match(observationRegex);

  // Combined "should we show a thought bubble at all?" — either legacy
  // ReAct markers OR `` reasoning chain.
  const hasThoughtAction = !!(
    thinkMatches.length > 0 || thoughtMatch || actionMatch || observationMatch
  );

  if (hasThoughtAction) {
    // Prefer `` content if present (it's the model's actual chain
    // of thought); otherwise fall back to the legacy "Thought:" line.
    const thoughtText = thinkText || (thoughtMatch ? thoughtMatch[1].trim() : "");
    const actionText = actionMatch ? actionMatch[1].trim() : "";
    const observationText = observationMatch ? observationMatch[1].trim() : "";

    let cleanContent = strippedContent;
    if (thoughtMatch) cleanContent = cleanContent.replace(thoughtMatch[0], "");
    if (actionMatch) cleanContent = cleanContent.replace(actionMatch[0], "");
    if (observationMatch) cleanContent = cleanContent.replace(observationMatch[0], "");
    cleanContent = cleanContent.trim();

    return {
      hasThoughtAction: true,
      thoughtText,
      actionText,
      observationText,
      cleanContent,
    };
  }

  return {
    hasThoughtAction: false,
    thoughtText: "",
    actionText: "",
    observationText: "",
    cleanContent: strippedContent,
  };
}

/* ── Component: Collapsible Thought & Action ─────────────────────────────────── */

function CollapsibleThoughtAction({
  thought,
  action,
  observation,
}: {
  thought?: string;
  action?: string;
  observation?: string;
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-charcoal/10 bg-gradient-to-br from-surface-card to-surface-bone/50 shadow-sm">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between px-3.5 py-2 hover:bg-surface-bone/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded bg-primary/10 text-primary">
            <Brain size={13} weight="fill" className={isExpanded ? "scale-110" : ""} />
          </div>
          <span className="font-ui text-xs font-semibold text-charcoal">
            Chain of Thought & Action
          </span>
        </div>
        {isExpanded ? (
          <CaretUp size={13} className="text-charcoal/60" />
        ) : (
          <CaretDown size={13} className="text-charcoal/60" />
        )}
      </button>

      <div
        className={`grid transition-[grid-template-rows] duration-250 ease-in-out ${
          isExpanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        }`}
      >
        <div className="overflow-hidden">
          <div className="border-t border-charcoal/5 px-3.5 py-3 space-y-3 bg-canvas/40">
            {thought && (
              <div>
                <span className="block font-ui text-[10px] font-bold uppercase tracking-wider text-charcoal/50 mb-1">
                  Thought
                </span>
                <p className="font-sans text-xs leading-relaxed text-ink/90 italic">
                  {thought}
                </p>
              </div>
            )}
            {action && (
              <div>
                <span className="block font-ui text-[10px] font-bold uppercase tracking-wider text-charcoal/50 mb-1">
                  Action
                </span>
                <pre className="rounded bg-canvas p-2 font-mono text-[11px] leading-relaxed text-primary overflow-x-auto">
                  {action}
                </pre>
              </div>
            )}
            {observation && (
              <div>
                <span className="block font-ui text-[10px] font-bold uppercase tracking-wider text-charcoal/50 mb-1">
                  Observation
                </span>
                <pre className="rounded bg-canvas p-2 font-mono text-[11px] leading-relaxed text-charcoal overflow-x-auto">
                  {observation}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Message Bubble ─────────────────────────────────────────────────────────── */

function MessageBubble({
  event,
  userName,
  allEvents,
  isStreaming = false,
  isLastAssistantMessage = false,
}: {
  event: MessageEvent;
  userName: string;
  allEvents?: AssistantEventData[];
  isStreaming?: boolean;
  isLastAssistantMessage?: boolean;
}) {
  const isUser = event.role === "user";
  const displayName = isUser ? userName : "Lumen AI";
  const avatarSeed = isUser ? userName : "Nexus";
  const avatarStyle = isUser ? "thumbs" : "bottts";
  const avatarUrl = `https://api.dicebear.com/7.x/${avatarStyle}/svg?seed=${encodeURIComponent(avatarSeed)}&backgroundColor=transparent`;

  const parsed = !isUser ? parseAssistantMessage(event.content) : null;
  
  // For streaming assistant messages, show typing indicator effect
  const showTypingIndicator = isStreaming && !isUser && !event.content.trim();

  // Store methods for tool panel
  const extractToolArtifact = useAssistantStore((s) => s._extractToolArtifact);
  const setToolPanelOpen = useUIStore((s) => s.setAssistantToolPanelOpen);

  // Find tool events for this message
  let toolsForThisMessage: any[] = [];
  if (!isUser && allEvents) {
    const msgIndex = allEvents.findIndex(e => e.id === event.id);
    if (msgIndex !== -1) {
      let lastUserIndex = -1;
      for (let i = msgIndex - 1; i >= 0; i--) {
        if (allEvents[i].type === "message" && (allEvents[i] as any).role === "user") {
          lastUserIndex = i;
          break;
        }
      }
      
      const turnTools = [];
      for (let i = lastUserIndex + 1; i < msgIndex; i++) {
        const e = allEvents[i];
        if (e.type === "tool" && (e as any).status === "called" && (e as any).result) {
          turnTools.push(e);
        }
      }
      
      toolsForThisMessage = turnTools;
    }
  }

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className="h-9 w-9 flex-shrink-0 overflow-hidden rounded-full bg-surface-bone">
        <Image
          src={avatarUrl}
          alt=""
          width={36}
          height={36}
          unoptimized
          className="h-full w-full"
        />
      </div>

      <div className={`max-w-[calc(100%-48px)] sm:max-w-[85%] min-w-0 break-words ${isUser ? "text-right" : ""}`}>
        <div className={`mb-1 px-1 flex items-center gap-2 ${isUser ? "justify-end" : ""}`}>
          <p className="font-ui text-xs italic text-charcoal">
            {displayName}
          </p>
          {!isUser && isLastAssistantMessage && (
            <IterationPanel title="" />
          )}
        </div>

        {parsed?.hasThoughtAction && (
          <CollapsibleThoughtAction
            thought={parsed.thoughtText}
            action={parsed.actionText}
            observation={parsed.observationText}
          />
        )}

        {toolsForThisMessage.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {toolsForThisMessage.map((tool, idx) => {
              // Pretty print tool names
              const nameMap: Record<string, string> = {
                list_projects: "Projects",
                search_papers: "Search Results",
                list_project_papers: "Saved Papers",
                list_matrix_rows: "Matrix",
                list_gaps: "Research Gaps",
                list_conflicts: "Conflicts",
                get_report: "Report",
                retrieve_evidence: "Evidence",
              };
              const label = nameMap[tool.function] || tool.function.split('_').map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
              
              return (
                <button
                  key={idx}
                  onClick={() => {
                    extractToolArtifact(tool);
                    setToolPanelOpen(true);
                  }}
                  className="flex items-center gap-1.5 rounded bg-surface-bone/80 px-2.5 py-1.5 font-ui text-xs font-medium text-charcoal hover:bg-surface-bone hover:text-ink transition-colors border border-charcoal/5"
                >
                  <ArrowSquareOut size={13} />
                  View {label}
                </button>
              );
            })}
          </div>
        )}

        {(isUser || parsed?.cleanContent) && (
          <div
            className={`overflow-hidden rounded-2xl px-4 py-3.5 ${
              isUser
                ? "bg-primary text-white rounded-tr-md"
                : "bg-surface-bone text-ink rounded-tl-md"
            }`}
          >
            <div
              className={`markdown-body assistant-message-markdown font-ui ${
                isUser ? "markdown-body-inverted" : ""
              }`}
            >
              {showTypingIndicator ? (
                <span className="flex gap-1">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-charcoal/40" style={{ animationDelay: "0ms" }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-charcoal/40" style={{ animationDelay: "150ms" }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-charcoal/40" style={{ animationDelay: "300ms" }} />
                </span>
              ) : (
                <ReactMarkdown 
                  remarkPlugins={[remarkGfm]} 
                  rehypePlugins={[
                    rehypeRaw, 
                    [rehypeTwemojify, { 
                      params: { 
                        folder: "svg", 
                        ext: ".svg" 
                      } 
                    }]
                  ]}
                >
                  {isUser ? event.content : parsed!.cleanContent}
                </ReactMarkdown>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

