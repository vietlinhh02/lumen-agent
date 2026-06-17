/**
 * ChatMessage - Renders a single message/event in the chat stream.
 * 
 * Handles all event types:
 * - message: text bubble (user or assistant)
 * - error: error message
 */

"use client";

import Image from "next/image";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  AssistantEventData,
  MessageEvent,
} from "@/lib/types/assistant";

interface ChatMessageProps {
  event: AssistantEventData;
  userName: string;
}

export function ChatMessage({ event, userName }: ChatMessageProps) {
  if (event.type !== "message") return null;
  return <MessageBubble event={event as MessageEvent} userName={userName} />;
}

/* ── Message Bubble ─────────────────────────────────────────────────────────── */

function MessageBubble({
  event,
  userName,
}: {
  event: MessageEvent;
  userName: string;
}) {
  const isUser = event.role === "user";
  const displayName = isUser ? userName : "Lumen AI";
  const avatarSeed = isUser ? userName : "lumen-assistant";
  const avatarStyle = isUser ? "thumbs" : "bottts-neutral";
  const avatarUrl = `https://api.dicebear.com/7.x/${avatarStyle}/svg?seed=${encodeURIComponent(avatarSeed)}`;

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

      <div className={`max-w-[min(78%,720px)] ${isUser ? "text-right" : ""}`}>
        <p className="mb-1 px-1 font-ui text-xs italic text-charcoal">
          {displayName}
        </p>
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
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {event.content}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
}
