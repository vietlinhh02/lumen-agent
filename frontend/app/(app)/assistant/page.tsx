/**
 * Assistant index page - redirects to the most recent session
 * or prompts to create a new one.
 */

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { useAuthStore } from "@/lib/stores/auth-store";

export default function AssistantPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const sessions = useAssistantStore((s) => s.sessions);
  const loadingSessions = useAssistantStore((s) => s.loadingSessions);
  const loadSessions = useAssistantStore((s) => s.loadSessions);
  const createSession = useAssistantStore((s) => s.createSession);

  useEffect(() => {
    if (!token) return;
    void loadSessions();
  }, [token, loadSessions]);

  useEffect(() => {
    if (!token || loadingSessions) return;

    if (sessions.length === 0) {
      const autoCreate = async () => {
        const session = await createSession();
        if (session) {
          router.replace(`/assistant/sessions/${session.id}`);
        }
      };
      void autoCreate();
    } else {
      // Navigate to most recent session
      const mostRecent = sessions[0];
      if (mostRecent) {
        router.replace(`/assistant/sessions/${mostRecent.id}`);
      }
    }
  }, [token, sessions, loadingSessions, router, createSession]);

  // Loading state (or while auto-creating session)
  return (
    <div className="flex items-center justify-center h-[60vh]">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-charcoal font-ui text-sm">Loading assistant...</p>
      </div>
    </div>
  );
}
