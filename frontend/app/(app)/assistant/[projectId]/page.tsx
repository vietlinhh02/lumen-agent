"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { AssistantProvider, useAssistantStore } from "@/lib/stores/assistantStore";
import { useAssistantWS } from "@/lib/hooks/useAssistantWS";
import { ChatPanel } from "@/components/assistant/ChatPanel";
import { PreviewPanel } from "@/components/assistant/PreviewPanel";
import { ProgressChecklist } from "@/components/assistant/ProgressChecklist";
import { AssistantHeader } from "@/components/assistant/AssistantHeader";
import { getDocument, listDocuments } from "@/lib/api/assistant";

function SessionInner() {
  const params = useParams<{ projectId: string }>();
  const projectId = params?.projectId as string;
  const { token } = useAuth();
  const { setIdentity, reset, handleEvent } = useAssistantStore();
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    reset();
    if (projectId) setIdentity(projectId, null);
  }, [projectId, reset, setIdentity]);

  useEffect(() => {
    if (!token || !projectId) return;
    (async () => {
      try {
        const list = await listDocuments(token);
        const doc = list.items.find((d) => d.project_id === projectId);
        if (doc) {
          setIdentity(projectId, doc.id);
          const detail = await getDocument(token, doc.id);
          handleEvent({
            type: "markdown_snapshot",
            content: detail.content_md,
            version: detail.version,
            title: detail.title,
          });
          if (detail.messages && detail.messages.length > 0) {
            handleEvent({ type: "message_history", messages: detail.messages });
          }
        }
      } catch (err) {
        console.error("Failed to load chat document", err);
      } finally {
        setLoaded(true);
      }
    })();
  }, [token, projectId, setIdentity, handleEvent]);

  useAssistantWS(loaded ? projectId : null, token);

  return (
    <div className="fixed inset-0 top-[60px] flex flex-col ml-0 xl:ml-[56px]">
      <AssistantHeader />
      <div className="flex-1 flex min-h-0">
        <div className="w-full md:w-[420px] shrink-0 flex flex-col border-r border-hairline">
          <ProgressChecklist />
          <div className="flex-1 min-h-0">
            <ChatPanel token={token || ""} />
          </div>
        </div>
        <div className="flex-1 min-w-0 hidden md:block">
          <PreviewPanel />
        </div>
      </div>
    </div>
  );
}

export default function AssistantSessionPage() {
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
      <SessionInner />
    </AssistantProvider>
  );
}
