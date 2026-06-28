"use client";

import { useMemo } from "react";
import { Step } from "react-joyride";
import { Tour } from "./Tour";

const STORAGE_KEY = "lumen-new-project-onboarding-completed";

export function NewProjectOnboardingTour() {
  const steps = useMemo<Step[]>(
    () => [
      {
        target: '[data-tour="new-project-welcome"]',
        content:
          "Create a new literature review project. A clear title and research question help the AI stay focused.",
        placement: "center",
        skipBeacon: true,
      },
      {
        target: '[data-tour="new-project-idea"]',
        content:
          "Stuck? Describe your research idea in any language and AI will generate a title, topic, and research question for you.",
        placement: "bottom",
      },
      {
        target: '[data-tour="new-project-form"]',
        content:
          "Review or edit the project details, then click Create Project to start your workspace.",
        placement: "top",
      },
    ],
    [],
  );

  return <Tour steps={steps} storageKey={STORAGE_KEY} startDelay={400} />;
}
