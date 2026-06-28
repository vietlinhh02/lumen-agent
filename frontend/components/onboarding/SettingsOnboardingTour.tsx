"use client";

import { useMemo } from "react";
import { Step } from "react-joyride";
import { Tour } from "./Tour";

const STORAGE_KEY = "lumen-settings-onboarding-completed";

export function SettingsOnboardingTour() {
  const steps = useMemo<Step[]>(
    () => [
      {
        target: '[data-tour="settings-welcome"]',
        content:
          "Manage your profile, preferences, and account settings from this page.",
        placement: "center",
        skipBeacon: true,
      },
      {
        target: '[data-tour="settings-tabs"]',
        content:
          "Switch between Profile, Admin, and Usage & Cost tabs. Admin tabs only appear for admin accounts.",
        placement: "bottom",
      },
      {
        target: '[data-tour="settings-content"]',
        content:
          "Update your information here. Changes are saved automatically or via the form's save button.",
        placement: "top",
      },
    ],
    [],
  );

  return <Tour steps={steps} storageKey={STORAGE_KEY} startDelay={400} />;
}
