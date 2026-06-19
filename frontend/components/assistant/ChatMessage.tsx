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
import { Brain, CaretDown, CaretUp } from "@phosphor-icons/react";

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
    return <MessageBubble event={event as MessageEvent} userName={userName} isStreaming={isStreaming} isLastAssistantMessage={isLastAssistantMessage} />;
  }
  
  // Handle thought events - render ThoughtBubble with turn-specific text
  if (event.type === "thought") {
    const isLastEvent = allEvents ? allEvents[allEvents.length - 1].id === event.id : false;
    const content = allEvents ? getAccumulatedThought(event as any, allEvents) : (event as any).delta;
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

/* ── Helper: Accumulate thought tokens for specific iteration & message turn ── */

function getAccumulatedThought(event: any, allEvents: AssistantEventData[]): string {
  const index = allEvents.findIndex((e) => e.id === event.id);
  if (index === -1) return event.delta || "";

  // Find the last user message index before this event
  let lastUserMsgIndex = 0;
  for (let i = index - 1; i >= 0; i--) {
    if (allEvents[i].type === "message" && (allEvents[i] as any).role === "user") {
      lastUserMsgIndex = i;
      break;
    }
  }

  // Accumulate all deltas for thought events in the same iteration between lastUserMsgIndex and index
  let text = "";
  for (let i = lastUserMsgIndex; i <= index; i++) {
    const e = allEvents[i];
    if (e.type === "thought" && (e as any).iteration === event.iteration) {
      text += (e as any).delta || "";
    }
  }
  return text;
}

/* ── Helper: Parse ReAct Thought & Action ───────────────────────────────────── */

function parseAssistantMessage(content: string) {
  const thoughtRegex = /(?:^|\n)\s*Thought:\s*([\s\S]*?)(?=(?:\n\s*Action:|\n\s*Observation:|$))/i;
  const actionRegex = /(?:^|\n)\s*Action:\s*([\s\S]*?)(?=(?:\n\s*Observation:|$))/i;
  const observationRegex = /(?:^|\n)\s*Observation:\s*([\s\S]*?)$/i;

  const thoughtMatch = content.match(thoughtRegex);
  const actionMatch = content.match(actionRegex);
  const observationMatch = content.match(observationRegex);

  const hasThoughtAction = !!(thoughtMatch || actionMatch || observationMatch);

  if (hasThoughtAction) {
    const thoughtText = thoughtMatch ? thoughtMatch[1].trim() : "";
    const actionText = actionMatch ? actionMatch[1].trim() : "";
    const observationText = observationMatch ? observationMatch[1].trim() : "";

    let cleanContent = content;
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
    cleanContent: content,
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
  isStreaming = false,
  isLastAssistantMessage = false,
}: {
  event: MessageEvent;
  userName: string;
  isStreaming?: boolean;
  isLastAssistantMessage?: boolean;
}) {
  const isUser = event.role === "user";
  const displayName = isUser ? userName : "Lumen AI";
  const avatarSeed = isUser ? userName : "lumen-assistant";
  const avatarStyle = isUser ? "thumbs" : "bottts-neutral";
  const avatarUrl = `https://api.dicebear.com/7.x/${avatarStyle}/svg?seed=${encodeURIComponent(avatarSeed)}`;

  const parsed = !isUser ? parseAssistantMessage(event.content) : null;
  
  // For streaming assistant messages, show typing indicator effect
  const showTypingIndicator = isStreaming && !isUser && !event.content.trim();

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

      <div className={`max-w-[calc(100%-48px)] sm:max-w-[85%] ${isUser ? "text-right" : ""}`}>
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
                  rehypePlugins={[rehypeRaw, rehypeTwemojify]}
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

