"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessageFE } from "@/lib/types";
import { ToolCallCard } from "./ToolCallCard";

const AI_AVATAR_URL =
  "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=LumenResearch&backgroundColor=fff3ed";
const USER_AVATAR_URL =
  "https://api.dicebear.com/7.x/thumbs/svg?seed=LumenResearcher&backgroundColor=e0f2fe";

export function MessageBubble({ message }: { message: ChatMessageFE }) {
  if (message.role === "tool_log") {
    return <ToolCallCard message={message} />;
  }
  const isUser = message.role === "user";
  return (
    <div className={`flex gap-1.5 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && <Avatar label="AI" tone="assistant" imageUrl={AI_AVATAR_URL} />}
      <div
        className={`max-w-[calc(100%-2.5rem)] rounded-2xl px-2.5 py-1.5 text-[13px] leading-snug md:max-w-[85%] md:px-3 ${
          isUser
            ? "bg-primary text-on-primary"
            : "bg-surface-card border border-hairline text-ink"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
              ul: ({ children }) => <ul className="mb-1.5 list-disc pl-5">{children}</ul>,
              ol: ({ children }) => <ol className="mb-1.5 list-decimal pl-5">{children}</ol>,
              code: ({ children }) => (
                <code className="rounded bg-surface-bone px-1 py-0.5 text-[0.85em]">
                  {children}
                </code>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </div>
      {isUser && <Avatar label="User" tone="user" imageUrl={USER_AVATAR_URL} />}
    </div>
  );
}

function Avatar({
  label,
  tone,
  imageUrl,
}: {
  label: string;
  tone: "assistant" | "user";
  imageUrl?: string;
}) {
  const classes =
    tone === "user"
      ? "bg-primary text-on-primary"
      : "bg-surface-card text-primary border border-hairline";

  return (
    <div
      className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center overflow-hidden rounded-full text-[10px] font-bold ${classes}`}
      aria-hidden="true"
      style={
        imageUrl
          ? {
              backgroundImage: `url(${imageUrl})`,
              backgroundPosition: "center",
              backgroundSize: "cover",
            }
          : undefined
      }
    >
      {imageUrl ? null : label}
    </div>
  );
}
