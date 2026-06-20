"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/lib/stores/auth-store";
import type { ProjectCreate } from "@/lib/types";

interface GeneratedMeta {
  title: string;
  topic: string;
  research_question: string | null;
}

export default function NewProjectPage() {
  const router = useRouter();
  const createProject = useProjectsStore((s) => s.createProject);

  const [idea, setIdea] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [researchQuestion, setResearchQuestion] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleGenerate() {
    if (!idea.trim()) return;
    setIsGenerating(true);
    const token = useAuthStore.getState().token;
    try {
      const meta = await apiFetch<GeneratedMeta>("/projects/generate-metadata", {
        method: "POST",
        body: JSON.stringify({ idea: idea.trim() }),
        headers: { Authorization: `Bearer ${token}` },
      });
      setTitle(meta.title);
      setTopic(meta.topic);
      setResearchQuestion(meta.research_question ?? "");
      toast.success("Fields generated successfully");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to generate. Please fill in manually."
      );
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    const body: ProjectCreate = {
      title: title.trim(),
      topic: topic.trim(),
      research_question: researchQuestion.trim() || null,
    };
    const created = await createProject(body);
    setIsSubmitting(false);
    if (created) {
      toast.success("Project created");
      router.push(`/projects/${created.id}`);
    } else {
      toast.error("Failed to create project");
    }
  }

  return (
    <div className="mx-auto max-w-[560px]">
      <div className="mb-12 animate-fade-in">
        <Link
          href="/projects"
          className="font-ui inline-flex items-center gap-1 text-sm font-semibold text-charcoal hover:text-ink transition-colors mb-4"
        >
          ← Projects
        </Link>
        <h1
          className="font-display text-[40px] font-bold leading-[1.0] text-ink animate-slide-up"
          style={{ letterSpacing: "-1px" }}
        >
          New Project
        </h1>
        <p className="mt-2 text-base leading-[1.5] text-charcoal animate-slide-up delay-100">
          Start a new literature review project.
        </p>
      </div>

      {/* ── AI Idea Input ──────────────────────────────────── */}
      <div className="mb-8 animate-slide-up delay-150">
        <label
          htmlFor="idea"
          className="font-ui mb-1.5 block text-sm font-semibold text-ink"
          style={{ letterSpacing: "-0.3px" }}
        >
          Describe your idea
        </label>
        <p className="text-sm text-charcoal mb-2.5">
          Describe your research idea in any language. AI will generate the fields below in English.
        </p>
        <textarea
          id="idea"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="e.g. I want to study how retrieval-augmented generation improves medical question answering compared to fine-tuned LLMs"
          className="focus-ring w-full rounded-[20px] bg-surface-card px-5 py-3.5 text-base text-ink placeholder:text-ash outline-none transition-shadow resize-y min-h-[80px]"
          style={{ border: "1px solid var(--hairline)" }}
        />
        <button
          type="button"
          onClick={handleGenerate}
          disabled={isGenerating || !idea.trim()}
          className="font-ui mt-2.5 inline-flex h-[40px] items-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-on-dark transition-all hover:bg-charcoal active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isGenerating ? (
            <>
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-on-dark border-t-transparent" />
              Generating…
            </>
          ) : (
            "Generate with AI"
          )}
        </button>
      </div>

      {/* ── Divider ────────────────────────────────────────── */}
      <div className="flex items-center gap-3 mb-6 animate-slide-up delay-200">
        <div className="flex-1 h-px bg-[var(--hairline)]" />
        <span className="font-ui text-xs font-semibold text-ash uppercase tracking-wider">
          Project details
        </span>
        <div className="flex-1 h-px bg-[var(--hairline)]" />
      </div>

      {/* ── Form Fields ────────────────────────────────────── */}
      <form onSubmit={handleSubmit} className="space-y-5 animate-slide-up delay-200">
        <div>
          <label
            htmlFor="title"
            className="font-ui mb-1.5 block text-sm font-semibold text-ink"
            style={{ letterSpacing: "-0.3px" }}
          >
            Title
          </label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={512}
            placeholder="e.g. Deep Learning for Medical Imaging"
            className="focus-ring h-[48px] w-full rounded-full bg-surface-card px-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
            style={{ border: "1px solid var(--hairline)" }}
          />
        </div>

        <div>
          <label
            htmlFor="topic"
            className="font-ui mb-1.5 block text-sm font-semibold text-ink"
            style={{ letterSpacing: "-0.3px" }}
          >
            Topic
          </label>
          <input
            id="topic"
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            required
            placeholder="e.g. Medical AI"
            className="focus-ring h-[48px] w-full rounded-full bg-surface-card px-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
            style={{ border: "1px solid var(--hairline)" }}
          />
        </div>

        <div>
          <label
            htmlFor="research_question"
            className="font-ui mb-1.5 block text-sm font-semibold text-ink"
            style={{ letterSpacing: "-0.3px" }}
          >
            Research Question{" "}
            <span className="font-normal text-ash">(optional)</span>
          </label>
          <textarea
            id="research_question"
            value={researchQuestion}
            onChange={(e) => setResearchQuestion(e.target.value)}
            rows={4}
            placeholder="e.g. How do CNNs compare to Vision Transformers in detecting pulmonary nodules?"
            className="focus-ring w-full rounded-[20px] bg-surface-card px-5 py-3.5 text-base text-ink placeholder:text-ash outline-none transition-shadow resize-y min-h-[120px]"
            style={{ border: "1px solid var(--hairline)" }}
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="font-ui h-[48px] w-full rounded-full bg-primary text-base font-semibold leading-[1.0] text-on-primary transition-colors hover:bg-primary-deep active:bg-primary-deep disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "Creating…" : "Create Project"}
        </button>
      </form>
    </div>
  );
}
