"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { AssistantProvider, useAssistantStore } from "@/lib/stores/assistantStore";
import { useAssistantWS } from "@/lib/hooks/useAssistantWS";
import { ChatPanel } from "@/components/assistant/ChatPanel";
import { PreviewPanel } from "@/components/assistant/PreviewPanel";
import { ProgressChecklist } from "@/components/assistant/ProgressChecklist";
import { AssistantHeader } from "@/components/assistant/AssistantHeader";

function AssistantEntryInner() {
  const router = useRouter();
  const { state, reset } = useAssistantStore();

  useEffect(() => {
    reset();
  }, [reset]);

  useAssistantWS("new", useAuth().token);

  useEffect(() => {
    if (state.projectId) {
      router.replace(`/assistant/${state.projectId}`);
    }
  }, [state.projectId, router]);

  return <AssistantLayout />;
}

function AssistantLayout() {
  return (
    <div className="fixed inset-0 top-[60px] flex flex-col ml-0 xl:ml-[56px]">
      <AssistantHeader />
      <div className="flex-1 flex min-h-0">
        <div className="w-full md:w-[420px] shrink-0 flex flex-col border-r border-hairline">
          <ProgressChecklist />
          <div className="flex-1 min-h-0">
            <ChatPanel token={useAuth().token || ""} />
          </div>
        </div>
        <div className="flex-1 min-w-0 hidden md:block">
          <PreviewPanel />
        </div>
      </div>
    </div>
  );
}

export default function AssistantEntryPage() {
  const { token } = useAuth();
  if (!token) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-60px)]">
        <p className="text-charcoal">Please log in to use the assistant.</p>
      </div>
    );
  }
  return (
    <AssistantProvider>
      <AssistantEntryInner />
    </AssistantProvider>
  );
}
