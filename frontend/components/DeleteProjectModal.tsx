"use client";

import { useEffect, useState, useRef } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";

export function DeleteProjectModal({
  projectId,
  onClose,
  onDeleted,
  token,
}: {
  projectId: string;
  onClose: () => void;
  onDeleted: () => void;
  token: string | null;
}) {
  const [isDeleting, setIsDeleting] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  async function handleDelete() {
    setIsDeleting(true);
    try {
      await apiFetch(`/projects/${projectId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success("Project deleted");
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete project");
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
        <h2 className="font-display text-[20px] font-bold leading-[1.2] text-ink"
          style={{ letterSpacing: "-0.5px" }}>
          Delete Project
        </h2>
        <p className="mt-2 text-sm leading-[1.6] text-charcoal">
          This will permanently delete the project and all its saved papers. This action cannot be undone.
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
            {isDeleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
