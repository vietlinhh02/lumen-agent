/**
 * ChatBox - Sticky-bottom input with Send/Stop buttons.
 */

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { ChatProjectPicker } from "./ChatProjectPicker";
import { PaperPlaneTilt, Stop, Plus, Globe } from "@phosphor-icons/react";

interface ChatBoxProps {
  onSend: (message: string, isDeepResearch: boolean) => Promise<void>;
  onStop: () => void;
  onNewChat?: () => void;
}

/** Max message length */
const MAX_LENGTH = 10000;

export function ChatBox({ onSend, onStop, onNewChat }: ChatBoxProps) {
  const [message, setMessage] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [isDeepResearch, setIsDeepResearch] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = useAssistantStore((s) => s.isStreaming);
  const error = useAssistantStore((s) => s.error);
  
  const isLimitReached = error?.includes("maximum limit of 30 messages");

  // Auto-resize textarea
  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
  }, [message]);

  // Auto-focus on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = useCallback(async () => {
    const trimmed = message.trim();
    if (!trimmed || isStreaming) return;

    setMessage("");
    await onSend(trimmed, isDeepResearch);
    if (isDeepResearch) {
      setIsDeepResearch(false);
    }

    // Refocus textarea
    setTimeout(() => {
      textareaRef.current?.focus();
    }, 0);
  }, [message, isStreaming, onSend, isDeepResearch]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Submit on Enter (but not Shift+Enter)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const canSend = message.trim().length > 0 && !isStreaming;
  const charCount = message.length;
  const isOverLimit = charCount > MAX_LENGTH;

  return (
    <div
      data-tour="assistant-chatbox"
      className={`relative rounded-2xl border transition-colors ${
        isFocused ? "border-primary/50" : "border-charcoal/20"
      } bg-surface-card`}
    >
      {/* Textarea */}
      <div className="flex items-end">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          placeholder="Ask me anything about your research..."
          rows={1}
          className="w-full resize-none bg-transparent px-4 py-3 font-ui text-sm text-ink placeholder:text-charcoal/50 focus:outline-none disabled:opacity-50"
          style={{ minHeight: "48px", maxHeight: "150px" }}
          disabled={isStreaming || isLimitReached}
        />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 pb-3 gap-2">
        {/* Project picker + character count */}
        <div className="flex items-center gap-2 min-w-0">
          <ChatProjectPicker />
          <button
            type="button"
            onClick={() => setIsDeepResearch(!isDeepResearch)}
            className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-colors border ${
              isDeepResearch
                ? "bg-primary/10 text-primary border-primary/30"
                : "bg-surface-elevated text-charcoal/70 border-charcoal/10 hover:bg-surface-hover"
            }`}
            title="Toggle Deep Research"
          >
            <Globe size={14} weight={isDeepResearch ? "fill" : "regular"} />
            Deep Research
          </button>
          <span
            className={`font-ui text-xs ${
              isOverLimit ? "text-red-500" : "text-charcoal/60"
            }`}
          >
            {charCount > 0 && `${charCount}/${MAX_LENGTH}`}
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              className="flex items-center gap-2 rounded-xl bg-red-500 px-4 py-2 font-ui text-sm font-medium text-white transition-all hover:bg-red-600"
            >
              <Stop size={16} weight="fill" />
              Stop
            </button>
          ) : (
            <>
              {onNewChat && isLimitReached && (
                <button
                  type="button"
                  onClick={onNewChat}
                  title="Start a new chat"
                  className="relative flex items-center gap-1.5 h-9 px-3 justify-center rounded-xl bg-primary text-white transition-all hover:bg-primary/90 hover:scale-105 shadow-md shadow-primary/20 animate-bounce"
                >
                  <Plus size={16} weight="bold" />
                  <span className="font-ui text-sm font-medium">New Chat</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => void handleSubmit()}
              disabled={!canSend || isOverLimit || isLimitReached}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 font-ui text-sm font-medium transition-all ${
                canSend && !isOverLimit && !isLimitReached
                  ? "bg-primary text-white hover:bg-primary/90"
                  : "bg-charcoal/20 text-charcoal/50 cursor-not-allowed"
              }`}
            >
              <PaperPlaneTilt size={16} weight="fill" />
              Send
            </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
