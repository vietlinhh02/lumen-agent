/**
 * Assistant index page - redirects to the most recent session
 * or prompts to create a new one.
 */

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { useAuthStore } from "@/lib/stores/auth-store";
import { ChatCircle } from "@phosphor-icons/react";

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
    if (!token || sessions.length === 0) return;

    // Navigate to most recent session
    const mostRecent = sessions[0];
    if (mostRecent) {
      router.replace(`/assistant/sessions/${mostRecent.id}`);
    }
  }, [token, sessions, router]);

  const handleNewSession = async () => {
    const session = await createSession();
    if (session) {
      router.push(`/assistant/sessions/${session.id}`);
    }
  };

  // Loading state
  if (!token || loadingSessions) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-charcoal font-ui text-sm">Loading assistant...</p>
        </div>
      </div>
    );
  }

  // Show new session button if no sessions exist
  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-6">
        <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary/10">
          <ChatCircle size={40} className="text-primary" weight="duotone" />
        </div>
        <div className="text-center">
          <h1 className="font-display text-2xl font-semibold text-ink mb-2">
            Welcome to Lumen Assistant
          </h1>
          <p className="text-charcoal font-ui text-sm max-w-md">
            Your AI research companion. Search papers, build matrices, detect gaps,
            and generate reports — all through natural conversation.
          </p>
        </div>
        <button
          onClick={handleNewSession}
          className="flex items-center gap-2 rounded-xl bg-primary px-6 py-3 font-ui font-medium text-white transition-all hover:bg-primary/90 hover:shadow-lg"
        >
          <ChatCircle size={20} weight="fill" />
          Start New Chat
        </button>
      </div>
    );
  }

  return null;
}
