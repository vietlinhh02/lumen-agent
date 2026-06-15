"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import { AssistantContextProvider } from "@/components/assistant/AssistantContext";
import { ChatPanel } from "@/components/assistant/ChatPanel";
import { PreviewPanel } from "@/components/assistant/PreviewPanel";
import { ProgressChecklist } from "@/components/assistant/ProgressChecklist";
import { AssistantHeader } from "@/components/assistant/AssistantHeader";
import { SessionSidebar } from "@/components/assistant/SessionSidebar";
import { SandboxPanel } from "@/components/assistant/SandboxPanel";
import { getDocument, listDocuments } from "@/lib/api/assistant";

export default function AssistantSessionPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params?.projectId as string;
  const { token } = useAuth();
  const { setIdentity, reset, handleEvent, state, togglePreview } =
    useAssistantStore();
  const [isMobile, setIsMobile] = useState(false);
  // Silence "unused" if togglePreview ever stops being called: it powers
  // the global header's "Show preview" button, which lives in AppShell.
  void togglePreview;

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
      }
    })();
  }, [token, projectId, setIdentity, handleEvent]);

  // Track viewport so we can swap the preview behaviour between desktop
  // (side-by-side) and mobile (preview replaces chat).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const hasDoc = Boolean(state.currentMarkdown);
  const previewOpen = hasDoc && !state.previewDismissed;

  if (!token) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-60px)]">
        <p className="text-charcoal">Please log in to use the assistant.</p>
      </div>
    );
  }

  // Mobile: when preview is open it replaces chat so the user can still read
  // the document; otherwise chat fills the available space.
  const showChat = !previewOpen || !isMobile;
  const showPreview = previewOpen;

  // SSE transport only requires projectId + token; we don't gate on `loaded`
  // because the chat can start before the document is fetched.
  return (
    <AssistantContextProvider projectId={projectId} token={token}>
      <div className="fixed inset-0 top-[60px] flex flex-col ml-0 xl:ml-[56px]">
        <AssistantHeader />
        <div className="flex-1 flex flex-col md:flex-row min-h-0 min-w-0">
          <SessionSidebar activeProjectId={projectId} />
          <div className="flex-1 min-w-0 min-h-0 flex flex-col">
            <div className="border-b border-hairline">
              <ProgressChecklist />
            </div>
            <div className="flex-1 min-h-0 min-w-0 flex">
              {showChat && (
                <div className="flex-1 min-w-0 min-h-0">
                  <ChatPanel />
                </div>
              )}
              {showPreview && (
                <div
                  className={
                    isMobile
                      ? "flex-1 min-w-0 min-h-0"
                      : "flex-1 min-w-0 min-h-0 border-l border-hairline"
                  }
                >
                  <PreviewPanel />
                </div>
              )}
            </div>
          </div>
        </div>
        <SandboxPanel />
      </div>
    </AssistantContextProvider>
  );
}
