"use client";

import { useState } from "react";
import { WaitEvent } from "@/lib/types/assistant";
import { PaperPlaneTilt } from "@phosphor-icons/react";

interface WaitEventPanelProps {
  event: WaitEvent;
  onSend: (message: string) => void;
}

export function WaitEventPanel({ event, onSend }: WaitEventPanelProps) {
  const [value, setValue] = useState(event.placeholder || "");

  return (
    <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4 my-4 animate-fade-in-up">
      <h3 className="text-sm font-semibold text-primary mb-3">
        {event.question || "Vui lòng xác nhận hoặc chỉnh sửa:"}
      </h3>
      
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="w-full bg-canvas border border-charcoal/20 rounded-xl p-3 text-sm focus:outline-none focus:border-primary/50 resize-y min-h-[100px] mb-3 font-ui"
        placeholder={event.placeholder || "Enter your response..."}
      />
      
      <div className="flex justify-end gap-2">
        {event.options?.map((opt) => (
          <button 
            key={opt}
            onClick={() => onSend(opt)}
            className="px-4 py-2 rounded-xl text-sm font-medium text-charcoal bg-surface-bone hover:bg-charcoal/10 transition-colors"
          >
            {opt}
          </button>
        ))}
        <button
          onClick={() => {
            if (value.trim()) {
              onSend(value);
            }
          }}
          disabled={!value.trim()}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white bg-primary hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <PaperPlaneTilt weight="fill" />
          Gửi
        </button>
      </div>
    </div>
  );
}
