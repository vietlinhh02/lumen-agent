"use client";

import { useMemo } from "react";
import { Step } from "react-joyride";
import { Tour } from "./Tour";

const STORAGE_KEY = "lumen-projects-list-onboarding-completed";

export function ProjectsListOnboardingTour() {
  const steps = useMemo<Step[]>(
    () => [
      {
        target: '[data-tour="projects-list-welcome"]',
        content:
          "All your research projects live here. Each project is an isolated workspace with its own papers, matrix, gaps, and reports.",
        placement: "center",
        skipBeacon: true,
      },
      {
        target: '[data-tour="projects-list-new"]',
        content:
          "Click here to start a new literature review project anytime.",
        placement: "bottom",
      },
      {
        target: '[data-tour="projects-list-filter"]',
        content:
          "Switch between All, Active, and Archived projects to keep things organized.",
        placement: "bottom",
      },
    ],
    [],
  );

  return <Tour steps={steps} storageKey={STORAGE_KEY} startDelay={400} />;
}
