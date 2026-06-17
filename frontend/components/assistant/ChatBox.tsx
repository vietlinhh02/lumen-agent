/**
 * ChatBox - Sticky-bottom input with Send/Stop buttons.
 */

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { PaperPlaneTilt, Stop } from "@phosphor-icons/react";

interface ChatBoxProps {
  onSend: (message: string) => Promise<void>;
  onStop: () => void;
}

/** Max message length */
const MAX_LENGTH = 10000;

export function ChatBox({ onSend, onStop }: ChatBoxProps) {
  const [message, setMessage] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = useAssistantStore((s) => s.isStreaming);

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
    await onSend(trimmed);

    // Refocus textarea
    setTimeout(() => {
      textareaRef.current?.focus();
    }, 0);
  }, [message, isStreaming, onSend]);

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
          className="w-full resize-none bg-transparent px-4 py-3 font-ui text-sm text-ink placeholder:text-charcoal/50 focus:outline-none"
          style={{ minHeight: "48px", maxHeight: "150px" }}
          disabled={isStreaming}
        />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 pb-3">
        {/* Character count */}
        <span
          className={`font-ui text-xs ${
            isOverLimit ? "text-red-500" : "text-charcoal/60"
          }`}
        >
          {charCount > 0 && `${charCount}/${MAX_LENGTH}`}
        </span>

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
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={!canSend || isOverLimit}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 font-ui text-sm font-medium transition-all ${
                canSend && !isOverLimit
                  ? "bg-primary text-white hover:bg-primary/90"
                  : "bg-charcoal/20 text-charcoal/50 cursor-not-allowed"
              }`}
            >
              <PaperPlaneTilt size={16} weight="fill" />
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
