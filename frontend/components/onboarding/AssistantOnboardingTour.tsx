"use client";

import { useMemo } from "react";
import { Step } from "react-joyride";
import { Tour } from "./Tour";

const STORAGE_KEY = "lumen-assistant-onboarding-completed";

export function AssistantOnboardingTour() {
  const steps = useMemo<Step[]>(
    () => [
      {
        target: '[data-tour="assistant-welcome"]',
        content:
          "Meet Lumen Assistant. Ask anything about your research — search papers, build matrices, detect gaps, or generate reports through chat.",
        placement: "center",
        skipBeacon: true,
      },
      {
        target: '[data-tour="assistant-sessions"]',
        content:
          "Your recent chat sessions live here. Switch between conversations without losing context.",
        placement: "right",
      },
      {
        target: '[data-tour="assistant-chatbox"]',
        content:
          "Type your question here. You can also pick a project so the assistant answers using that project's papers and matrix.",
        placement: "top",
      },
    ],
    [],
  );

  return <Tour steps={steps} storageKey={STORAGE_KEY} startDelay={400} />;
}
