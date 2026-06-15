"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAssistantStore } from "@/lib/stores/assistantStore";

export function PreviewPanel() {
  const { state } = useAssistantStore();

  if (!state.currentMarkdown) {
    return (
      <div className="h-full flex items-center justify-center bg-surface-bone/30 px-12 text-center">
        <div className="text-charcoal/60 text-sm">
          <p className="font-medium mb-2">No document yet</p>
          <p>The Markdown literature review will appear here once the agent finishes writing it.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-canvas px-5 py-5 md:px-8 md:py-6">
      <article className="prose prose-sm max-w-none text-ink prose-headings:font-display prose-a:text-primary prose-code:text-ink prose-pre:bg-surface-dark">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {state.currentMarkdown}
        </ReactMarkdown>
      </article>
    </div>
  );
}
