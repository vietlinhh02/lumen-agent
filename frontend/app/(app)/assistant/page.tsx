"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createDocument } from "@/lib/api/assistant";
import { useAuth } from "@/lib/auth";
import { useAssistantStore } from "@/lib/stores/assistantStore";

export default function AssistantEntryPage() {
  const { token } = useAuth();
  const { reset } = useAssistantStore();
  const router = useRouter();
  const creatingRef = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || creatingRef.current) return;
    creatingRef.current = true;
    reset();

    createDocument(token)
      .then((doc) => {
        router.replace(`/assistant/${doc.project_id}`);
      })
      .catch((err: unknown) => {
        creatingRef.current = false;
        setError(err instanceof Error ? err.message : "Could not create session");
      });
  }, [token, reset, router]);

  if (!token) {
    return (
      <div className="flex h-[calc(100vh-60px)] items-center justify-center">
        <p className="text-charcoal">Please log in to use the assistant.</p>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-60px)] items-center justify-center px-6">
      <div className="w-full max-w-sm rounded-lg border border-hairline bg-surface-card p-5 text-center">
        <p className="text-sm font-semibold text-ink">
          {error ? "Could not create session" : "Creating a new session..."}
        </p>
        {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      </div>
    </div>
  );
}
