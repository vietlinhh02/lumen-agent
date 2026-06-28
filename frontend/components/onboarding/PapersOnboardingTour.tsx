"use client";

import { useMemo } from "react";
import { Step } from "react-joyride";
import { Tour } from "./Tour";

const STORAGE_KEY = "lumen-papers-onboarding-completed";

export function PapersOnboardingTour() {
  const steps = useMemo<Step[]>(
    () => [
      {
        target: '[data-tour="papers-welcome"]',
        content:
          "This is your saved papers library. Every paper you save across projects is collected here.",
        placement: "center",
        skipBeacon: true,
      },
      {
        target: '[data-tour="papers-filters"]',
        content:
          "Search by title or filter by project to find the paper you need.",
        placement: "bottom",
      },
      {
        target: '[data-tour="papers-table"]',
        content:
          "Click any paper to open it, view metadata, or jump back to its project workspace.",
        placement: "top",
      },
    ],
    [],
  );

  return <Tour steps={steps} storageKey={STORAGE_KEY} startDelay={400} />;
}
