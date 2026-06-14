"use client";

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
    <div className="h-full overflow-y-auto bg-canvas px-8 py-6">
      <pre className="text-sm text-ink whitespace-pre-wrap font-sans">
        {state.currentMarkdown}
      </pre>
    </div>
  );
}
