"use client";

import { useEffect, useRef, useState } from "react";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import { useAssistantContext } from "./AssistantContext";
import { MessageBubble } from "./MessageBubble";
import { ToolLog } from "./ToolLog";

export function ChatPanel() {
  const { state, appendLocalMessage } = useAssistantStore();
  const { sendMessage, stop, connected } = useAssistantContext();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const send = () => {
    if (!input.trim() || !connected) return;
    const text = input.trim();
    appendLocalMessage({ role: "user", content: text, created_at: new Date().toISOString() });
    void sendMessage(text);
    setInput("");
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const onStop = () => {
    void stop();
  };

  const agentBusy = state.agentStatus === "running" || state.agentStatus === "thinking";
  const disabled = !connected || agentBusy;
  const showThinking = agentBusy && !state.streamingMessage;
  const placeholder = connected
    ? "Ask the agent or request an edit..."
    : "Disconnected. Refresh or log in again.";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [state.messages.length, state.streamingMessage, showThinking]);

  return (
    <div className="flex flex-col h-full bg-canvas">
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 md:px-4">
        {state.messages.length === 0 && (
          <div className="text-sm text-charcoal/70 text-center mt-10 px-3 md:mt-12 md:px-6">
            Describe a research topic to start. The agent will create a project, find papers,
            build a literature matrix, and write a Markdown review.
          </div>
        )}
        {state.messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        {state.streamingMessage && (
          <MessageBubble
            message={{
              role: "assistant",
              content: state.streamingMessage,
              created_at: new Date().toISOString(),
            }}
          />
        )}
        {showThinking && (
          <MessageBubble
            message={{
              role: "assistant",
              content: "AI đang thinking...",
              created_at: new Date().toISOString(),
            }}
          />
        )}
        <div ref={bottomRef} />
      </div>
      <ToolLog />
      <div className="border-t border-hairline px-2 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] flex items-end gap-2 bg-canvas md:px-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          rows={2}
          placeholder={placeholder}
          className="min-w-0 flex-1 resize-none rounded-lg border border-hairline bg-surface-card px-3 py-2 text-sm focus:outline-none focus:border-primary"
          disabled={disabled}
        />
        {agentBusy ? (
          <button
            onClick={onStop}
            className="shrink-0 rounded-full bg-red-500 text-white px-3 py-2 text-sm font-medium hover:bg-red-600 md:px-4"
          >
            Stop
          </button>
        ) : (
          <button
            onClick={send}
            disabled={!input.trim() || !connected}
            className="shrink-0 rounded-full bg-primary text-on-primary px-3 py-2 text-sm font-semibold hover:bg-primary-deep disabled:opacity-50 md:px-4"
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}
