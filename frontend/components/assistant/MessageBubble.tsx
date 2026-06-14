"use client";

import type { ChatMessageFE } from "@/lib/types";

export function MessageBubble({ message }: { message: ChatMessageFE }) {
  if (message.role === "tool_log") {
    return (
      <div className="text-xs text-charcoal/80 italic px-3 py-1 border-l-2 border-hairline">
        {message.content}
      </div>
    );
  }
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
          isUser
            ? "bg-primary text-on-primary"
            : "bg-surface-card border border-hairline text-ink"
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}
