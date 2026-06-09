"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type { ProjectCreate, ProjectResponse } from "@/lib/types";

export default function NewProjectPage() {
  const { token } = useAuth();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [researchQuestion, setResearchQuestion] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const body: ProjectCreate = {
        title: title.trim(),
        topic: topic.trim(),
        research_question: researchQuestion.trim() || null,
      };
      await apiFetch<ProjectResponse>("/projects", {
        method: "POST",
        body: JSON.stringify(body),
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success("Project created");
      router.push("/projects");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setIsSubmitting(false);
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
