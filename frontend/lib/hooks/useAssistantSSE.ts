"use client";

import { useCallback, useEffect, useRef } from "react";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import type { AssistantEvent } from "@/lib/types";

/**
 * useAssistantSSE — connect the assistant page to the SSE backend.
 *
 * Lifecycle:
 *  - On mount (and whenever projectId/token change), sets
 *    `state.connected = true` immediately. The actual streaming only
 *    happens when the user calls `sendMessage()`.
 *  - Each `sendMessage()` opens a new POST /api/assistant/message SSE
 *    stream and feeds events into the same store handlers the WS hook
 *    used to. Stop is a separate POST.
 *  - If the stream drops mid-turn, we surface a transient "reconnecting"
 *    state. The browser's fetch will only retry the POST on explicit
 *    user action — there's no transparent resume because the agent
 *    loop is stateful and a partial re-POST would duplicate work.
 */
export function useAssistantSSE(
  projectId: string | "new" | null,
  token: string | null,
) {
  const { setConnected, handleEvent } = useAssistantStore();
  const projectIdRef = useRef<string | null>(null);
  const activeStreamRef = useRef<AbortController | null>(null);
  const connected = Boolean(projectId && token);

  useEffect(() => {
    projectIdRef.current = projectId ?? null;
    // SSE "connected" means we *can* connect — there's no persistent
    // socket, so we mark it ready as soon as we have a project + token.
    setConnected(Boolean(projectId && token));

    return () => {
      // Cancel any in-flight stream when the component unmounts
      activeStreamRef.current?.abort();
      activeStreamRef.current = null;
      setConnected(false);
    };
  }, [projectId, token, setConnected]);

  const sendMessage = useCallback(
    async (content: string): Promise<void> => {
      const pid = projectIdRef.current;
      if (!pid || !token || !content.trim()) return;

      // Cancel any prior in-flight stream
      activeStreamRef.current?.abort();
      const ac = new AbortController();
      activeStreamRef.current = ac;

      try {
        const res = await fetch("/api/assistant/message", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ project_id: pid, content }),
          signal: ac.signal,
        });

        if (!res.ok || !res.body) {
          handleEvent({
            type: "error",
            message: `Assistant request failed: ${res.status}`,
            code: "sse_http_error",
          });
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let currentEvent = "message";
        let currentDataLines: string[] = [];

        const flushEvent = () => {
          if (!currentDataLines.length) {
            currentEvent = "message";
            return;
          }
          const dataStr = currentDataLines.join("\n");
          currentDataLines = [];
          try {
            const parsed: unknown = JSON.parse(dataStr);
            // Honor the explicit `type` from server, fall back to event name
            const ev: AssistantEvent =
              parsed && typeof parsed === "object" && "type" in parsed
                ? (parsed as AssistantEvent)
                : ({ type: currentEvent, ...(parsed as object) } as AssistantEvent);
            handleEvent(ev);
          } catch (err) {
            console.error("Failed to parse SSE data:", err, dataStr);
          }
          currentEvent = "message";
        };

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE frames are separated by a blank line ("\n\n")
          let idx: number;
          while ((idx = buffer.indexOf("\n\n")) !== -1) {
            const frame = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);

            for (const line of frame.split("\n")) {
              if (!line) continue;
              if (line.startsWith(":")) {
                // SSE comment (heartbeat) — ignore
                continue;
              }
              if (line.startsWith("event:")) {
                currentEvent = line.slice(6).trim();
              } else if (line.startsWith("data:")) {
                currentDataLines.push(line.slice(5).trimStart());
              }
            }
            flushEvent();
          }
        }
      } catch (err) {
        if ((err as { name?: string })?.name === "AbortError") {
          // User-initiated cancel — silent
          return;
        }
        handleEvent({
          type: "error",
          message: (err as Error).message || "SSE connection error",
          code: "sse_network_error",
        });
      } finally {
        if (activeStreamRef.current === ac) {
          activeStreamRef.current = null;
        }
      }
    },
    [token, handleEvent],
  );

  const stop = useCallback(async (): Promise<void> => {
    const pid = projectIdRef.current;
    if (!pid || !token) return;

    // 1) Abort the in-flight fetch (cuts the client side immediately)
    activeStreamRef.current?.abort();
    activeStreamRef.current = null;

    if (pid === "new") {
      handleEvent({ type: "stopped" });
      return;
    }

    // 2) Tell the server to stop the runner (sends a `stopped` event
    //    to any other active streams; harmless if no run is in flight)
    try {
      const res = await fetch("/api/assistant/stop", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ project_id: pid }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail = typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`;
        handleEvent({
          type: "error",
          message: `Stop failed: ${detail}`,
          code: "stop_failed",
        });
        return;
      }
      handleEvent({ type: "stopped" });
    } catch {
      // Best-effort
    }
  }, [token, handleEvent]);

  return {
    connected,
    sendMessage,
    stop,
  };
}
