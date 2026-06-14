"use client";

import { useEffect } from "react";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import type { AssistantEvent } from "@/lib/types";

const WS_URL = process.env.NEXT_PUBLIC_API_WS_URL || "ws://localhost:8010";

export function useAssistantWS(
  projectId: string | "new" | null,
  token: string | null,
) {
  const { setWs, setConnected, handleEvent } = useAssistantStore();

  useEffect(() => {
    if (!projectId || !token) return;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const connect = () => {
      ws = new WebSocket(
        `${WS_URL}/api/assistant/ws?project_id=${projectId}&token=${encodeURIComponent(token)}`,
      );
      setWs(ws);

      ws.onopen = () => {
        setConnected(true);
        attempts = 0;
      };
      ws.onclose = () => {
        setConnected(false);
        attempts += 1;
        const delay = Math.min(30000, 1000 * Math.pow(2, attempts));
        reconnectTimer = setTimeout(connect, delay);
      };
      ws.onerror = () => {
        ws?.close();
      };
      ws.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data) as AssistantEvent;
          handleEvent(event);
        } catch (err) {
          console.error("Failed to parse WS message", err);
        }
      };
    };

    connect();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
      setWs(null);
      setConnected(false);
    };
  }, [projectId, token, setWs, setConnected, handleEvent]);
}
