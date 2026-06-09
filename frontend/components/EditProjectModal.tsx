"use client";

import { useEffect, useState, useRef, type FormEvent } from "react";
import { toast } from "sonner";
import { X } from "@phosphor-icons/react";
import { apiFetch } from "@/lib/api";
import type { ProjectResponse } from "@/lib/types";

export function EditProjectModal({
  project,
  onClose,
  onSaved,
  token,
}: {
  project: ProjectResponse;
  onClose: () => void;
  onSaved: (updated: ProjectResponse) => void;
  token: string | null;
}) {
  const [title, setTitle] = useState(project.title);
  const [topic, setTopic] = useState(project.topic);
  const [researchQuestion, setResearchQuestion] = useState(project.research_question || "");
  const [status, setStatus] = useState(project.status);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const body: Record<string, string> = {};
      if (title.trim() !== project.title) body.title = title.trim();
      if (topic.trim() !== project.topic) body.topic = topic.trim();
      const newRQ = researchQuestion.trim() || null;
      if (newRQ !== (project.research_question || null)) body.research_question = newRQ || "";
      if (status !== project.status) body.status = status;

      if (Object.keys(body).length === 0) {
        onClose();
        return;
      }

      const updated = await apiFetch<ProjectResponse>(`/projects/${project.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success("Project updated");
      onSaved(updated);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update project");
    } finally {
      setIsSubmitting(false);
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
        className="w-full max-w-[500px] rounded-[16px] bg-surface-card p-8 shadow-xl animate-scale-in"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <div className="mb-6 flex items-center justify-between">
          <h2 className="font-display text-[24px] font-bold leading-[1.0] text-ink"
            style={{ letterSpacing: "-0.5px" }}>
            Edit Project
          </h2>
          <button
            onClick={onClose}
            className="flex h-[32px] w-[32px] items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
          >
            <X size={16} weight="bold" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="edit-title" className="font-ui mb-1.5 block text-sm font-semibold text-ink" style={{ letterSpacing: "-0.3px" }}>
              Title
            </label>
            <input
              id="edit-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              maxLength={512}
              className="focus-ring h-[48px] w-full rounded-full bg-surface-card px-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
              style={{ border: "1px solid var(--hairline)" }}
            />
          </div>

          <div>
            <label htmlFor="edit-topic" className="font-ui mb-1.5 block text-sm font-semibold text-ink" style={{ letterSpacing: "-0.3px" }}>
              Topic
            </label>
            <input
              id="edit-topic"
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              required
              className="focus-ring h-[48px] w-full rounded-full bg-surface-card px-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
              style={{ border: "1px solid var(--hairline)" }}
            />
          </div>

          <div>
            <label htmlFor="edit-rq" className="font-ui mb-1.5 block text-sm font-semibold text-ink" style={{ letterSpacing: "-0.3px" }}>
              Research Question <span className="font-normal text-ash">(optional)</span>
            </label>
            <textarea
              id="edit-rq"
              value={researchQuestion}
              onChange={(e) => setResearchQuestion(e.target.value)}
              rows={3}
              className="focus-ring w-full rounded-[16px] bg-surface-card px-5 py-3 text-base text-ink placeholder:text-ash outline-none transition-shadow resize-y min-h-[80px]"
              style={{ border: "1px solid var(--hairline)" }}
            />
          </div>

          <div>
            <label className="font-ui mb-1.5 block text-sm font-semibold text-ink" style={{ letterSpacing: "-0.3px" }}>
              Status
            </label>
            <div className="flex gap-2">
              {["active", "archived"].map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStatus(s)}
                  className={`font-ui rounded-full px-4 py-2 text-[13px] font-semibold transition-all duration-200 ${
                    status === s
                      ? "bg-ink text-on-dark"
                      : "bg-surface-bone text-charcoal hover:text-ink"
                  }`}
                >
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="font-ui h-[44px] flex-1 rounded-full bg-surface-bone text-sm font-semibold text-charcoal hover:text-ink transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="font-ui h-[44px] flex-1 rounded-full bg-primary text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSubmitting ? "Saving…" : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
