"use client";

import { useState } from "react";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import { MessageBubble } from "./MessageBubble";
import { ToolLog } from "./ToolLog";

interface Props {
  token: string;
}

export function ChatPanel({ token: _token }: Props) {
  const { state, appendLocalMessage } = useAssistantStore();
  const [input, setInput] = useState("");

  const send = () => {
    if (!input.trim() || !state.ws) return;
    const text = input.trim();
    appendLocalMessage({ role: "user", content: text, created_at: new Date().toISOString() });
    state.ws.send(JSON.stringify({ type: "user_message", content: text }));
    setInput("");
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const stop = () => {
    state.ws?.send(JSON.stringify({ type: "stop" }));
  };

  const disabled = !state.ws || state.agentStatus === "running" || state.agentStatus === "thinking";

  return (
    <div className="flex flex-col h-full bg-canvas">
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {state.messages.length === 0 && (
          <div className="text-sm text-charcoal/70 text-center mt-12 px-6">
            Describe a research topic to start. The agent will create a project, find papers,
            build a literature matrix, and write a Markdown review.
          </div>
        )}
        {state.messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
      </div>
      <ToolLog />
      <div className="border-t border-hairline px-3 py-2 flex items-end gap-2 bg-canvas">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          rows={2}
          placeholder="Ask the agent or request an edit…"
          className="flex-1 resize-none rounded-lg border border-hairline bg-surface-card px-3 py-2 text-sm focus:outline-none focus:border-primary"
          disabled={disabled}
        />
        {state.agentStatus === "running" || state.agentStatus === "thinking" ? (
          <button
            onClick={stop}
            className="rounded-full bg-red-500 text-white px-4 py-2 text-sm font-medium hover:bg-red-600"
          >
            Stop
          </button>
        ) : (
          <button
            onClick={send}
            disabled={!input.trim() || !state.ws}
            className="rounded-full bg-primary text-on-primary px-4 py-2 text-sm font-semibold hover:bg-primary-deep disabled:opacity-50"
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}
