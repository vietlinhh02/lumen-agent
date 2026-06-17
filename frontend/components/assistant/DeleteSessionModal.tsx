"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { Trash } from "@phosphor-icons/react";

interface DeleteSessionModalProps {
  sessionId: string;
  sessionTitle: string;
  onClose: () => void;
}

export function DeleteSessionModal({
  sessionId,
  sessionTitle,
  onClose,
}: DeleteSessionModalProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const deleteSession = useAssistantStore((s) => s.deleteSession);
  const activeSessionId = useAssistantStore((s) => s.activeSessionId);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  async function handleDelete() {
    setIsDeleting(true);
    const success = await deleteSession(sessionId);
    
    if (success) {
      // If deleting the active session, redirect to assistant index
      if (activeSessionId === sessionId) {
        router.push("/assistant");
      }
      onClose();
    } else {
      setIsDeleting(false);
    }
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm animate-fade-in"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div
        className="w-full max-w-[400px] rounded-[16px] bg-surface-card p-8 shadow-xl animate-scale-in"
        style={{ border: "1px solid var(--hairline)" }}
      >
        {/* Icon */}
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-error/10 mb-4">
          <Trash size={28} className="text-error" weight="duotone" />
        </div>

        <h2 className="font-display text-[20px] font-bold leading-[1.2] text-ink"
          style={{ letterSpacing: "-0.5px" }}>
          Delete Chat
        </h2>
        
        <p className="mt-3 text-sm leading-[1.6] text-charcoal">
          Are you sure you want to delete <span className="font-medium text-ink">&ldquo;{sessionTitle || "this chat"}&rdquo;</span>? 
          This will permanently remove all messages and cannot be undone.
        </p>

        <div className="mt-6 flex gap-3">
          <button
            onClick={onClose}
            disabled={isDeleting}
            className="font-ui h-[44px] flex-1 rounded-full bg-surface-bone text-sm font-semibold text-charcoal hover:text-ink transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            className="font-ui h-[44px] flex-1 rounded-full bg-error text-sm font-semibold text-white transition-colors hover:opacity-90 disabled:opacity-50"
          >
            {isDeleting ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Deleting…
              </span>
            ) : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
