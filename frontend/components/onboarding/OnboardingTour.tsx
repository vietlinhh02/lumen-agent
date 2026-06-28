"use client";

import { useMemo } from "react";
import { Step } from "react-joyride";
import { Tour } from "./Tour";

const STORAGE_KEY = "lumen-onboarding-completed";

export function OnboardingTour() {
  const steps = useMemo<Step[]>(
    () => [
      {
        target: '[data-tour="welcome"]',
        content:
          "Welcome to Lumen! This is your AI-powered literature review workspace.",
        placement: "center",
        skipBeacon: true,
      },
      {
        target: '[data-tour="sidebar"]',
        content:
          "Use the sidebar to navigate between Dashboard, Projects, Saved Papers, Assistant, and Settings.",
        placement: "right",
      },
      {
        target: '[data-tour="stats-grid"]',
        content:
          "Track your research progress at a glance: projects, papers, matrix rows, gaps, and reports.",
        placement: "bottom",
      },
      {
        target: '[data-tour="projects-list"]',
        content:
          "Your projects live here. Each card shows the next recommended action to move your review forward.",
        placement: "top",
      },
      {
        target: '[data-tour="quick-actions"]',
        content:
          "Jump straight into Search, Matrix, Gaps, or Review for your active project.",
        placement: "top",
      },
    ],
    [],
  );

  return (
    <Tour
      steps={steps}
      storageKey={STORAGE_KEY}
      minWidth={1280}
      startDelay={400}
    />
  );
}
