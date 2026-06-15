"use client";

import { createContext, useContext } from "react";
import { useAssistantSSE } from "@/lib/hooks/useAssistantSSE";

type AssistantContextValue = {
  connected: boolean;
  sendMessage: (content: string) => Promise<void>;
  stop: () => Promise<void>;
};

const AssistantContext = createContext<AssistantContextValue | null>(null);

export function AssistantContextProvider({
  projectId,
  token,
  children,
}: {
  projectId: string | "new" | null;
  token: string | null;
  children: React.ReactNode;
}) {
  const value = useAssistantSSE(projectId, token);
  return (
    <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>
  );
}

export function useAssistantContext(): AssistantContextValue {
  const ctx = useContext(AssistantContext);
  if (!ctx) {
    throw new Error(
      "useAssistantContext must be used inside <AssistantContextProvider>",
    );
  }
  return ctx;
}
