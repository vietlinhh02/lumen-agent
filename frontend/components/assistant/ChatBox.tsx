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
  const deepResearchState = useAssistantStore((s) => s._deepResearchState);
  const isDeepResearchRunning = deepResearchState?.status === "running";
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
    if (!trimmed || isStreaming || isDeepResearchRunning) return;

    setMessage("");

    if (isDeepResearch) {
      // Store the initial research message so ConfirmProjectPanel can use it
      useAssistantStore.setState({ _initialResearchMessage: trimmed });
    }

    await onSend(trimmed, isDeepResearch);

    // Refocus textarea
    setTimeout(() => {
      textareaRef.current?.focus();
    }, 0);
  }, [message, isStreaming, isDeepResearchRunning, onSend, isDeepResearch]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Submit on Enter (but not Shift+Enter)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const canSend = message.trim().length > 0 && !isStreaming && !isDeepResearchRunning;
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
          placeholder={isDeepResearchRunning ? "Deep Research is running, please wait..." : "Ask me anything about your research..."}
          rows={1}
          className="w-full resize-none bg-transparent px-4 py-3 font-ui text-sm text-ink placeholder:text-charcoal/50 focus:outline-none disabled:opacity-50"
          style={{ minHeight: "48px", maxHeight: "150px" }}
          disabled={isStreaming || isDeepResearchRunning || isLimitReached}
        />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 pb-3 gap-2">
        {/* Project picker + character count */}
        <div className="flex items-center gap-2 min-w-0">
          <ChatProjectPicker />
          <div className="relative group cursor-not-allowed">
            <button
              type="button"
              disabled={true}
              className="flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium bg-surface-elevated text-charcoal/40 border border-charcoal/10 opacity-50 pointer-events-none"
            >
              <Globe size={14} weight="regular" />
              Deep Research
            </button>
            <div className="absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 scale-95 opacity-0 transition-all duration-200 pointer-events-none group-hover:scale-100 group-hover:opacity-100 whitespace-nowrap rounded-lg bg-charcoal px-2.5 py-1 text-[10px] font-medium text-white shadow-md border border-charcoal/20">
              Feature in development
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-charcoal" />
            </div>
          </div>
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
