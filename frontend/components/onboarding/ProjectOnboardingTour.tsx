"use client";

import { useMemo } from "react";
import { Step } from "react-joyride";
import { Tour } from "./Tour";

const STORAGE_KEY = "lumen-project-onboarding-completed";

export function ProjectOnboardingTour() {
  const steps = useMemo<Step[]>(
    () => [
      {
        target: '[data-tour="project-welcome"]',
        content:
          "This is your project workspace. Everything about your literature review lives here.",
        placement: "center",
        skipBeacon: true,
      },
      {
        target: '[data-tour="project-tabs"]',
        content:
          "Follow the pipeline tabs: Search → Papers → Matrix → Map → Gaps → Reports. Locked tabs unlock automatically as you progress.",
        placement: "bottom",
      },
      {
        target: '[data-tour="project-progress"]',
        content:
          "This card always shows your next recommended action. Click the primary button to keep moving forward.",
        placement: "bottom",
      },
      {
        target: '[data-tour="project-snapshot"]',
        content:
          "Track counts for papers, matrix rows, gaps, conflicts, and generated reports at a glance.",
        placement: "top",
      },
      {
        target: '[data-tour="project-ask"]',
        content:
          "Stuck? Ask the project-aware assistant for help with papers, matrix, or gaps.",
        placement: "bottom",
      },
    ],
    [],
  );

  return (
    <Tour
      steps={steps}
      storageKey={STORAGE_KEY}
      startDelay={400}
    />
  );
}
